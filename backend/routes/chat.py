import os
import re
import json
import time
import select
import logging
import threading
from typing import Optional, List

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.session import SessionManager
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner
from backend.models.stream_state import StreamState
from backend.services.chat_repository import ChatRepository
from backend.services.stream_processor import StreamProcessor
from backend.services.slack.notifier import notify_completion

from backend.ai_middleware.config import get_settings as get_middleware_settings
from backend.ai_middleware.providers.openai.chat import OpenAIChatProvider
from backend.ai_middleware.models.chat import ChatMessage, MessageRole

log = logging.getLogger('chat')
chat_router = APIRouter()


# Pydantic models for request validation
class ChatStreamRequest(BaseModel):
    message: str
    workspace: Optional[str] = None
    chatId: Optional[str] = None
    history: Optional[List[dict]] = None


class ChatResetRequest(BaseModel):
    workspace: Optional[str] = None


# Braille spinner characters used by auggie for status indicators
_SPINNER_CHARS_RE = re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞]')

# Mapping of special Unicode chars to ASCII equivalents for terminal safety
_UNICODE_TO_ASCII_MAP = {
    '●': '*',   # Response marker → asterisk
    '•': '-',   # Bullet → dash
    '⎿': '|',   # Continuation marker → pipe
    '›': '>',   # Prompt char → greater-than
    '╭': '+',   # Box corners → plus
    '╮': '+',
    '╯': '+',
    '╰': '+',
    '│': '|',   # Vertical box → pipe
    '─': '-',   # Horizontal box → dash
}


def _sanitize_message(message: str) -> str:
    # Normalize newlines
    sanitized = message.replace('\n', ' ').replace('\r', ' ')

    # Remove spinner characters that could confuse status detection
    sanitized = _SPINNER_CHARS_RE.sub('', sanitized)

    # Convert Unicode special chars to ASCII equivalents
    for unicode_char, ascii_char in _UNICODE_TO_ASCII_MAP.items():
        sanitized = sanitized.replace(unicode_char, ascii_char)

    return sanitized


# Global abort flag for current streaming request
_abort_flag = threading.Event()


def _log(msg: str) -> None:
    log.info(msg)
    print(f"[CHAT] {msg}", flush=True)


class SSEFormatter:
    @staticmethod
    def send(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    @staticmethod
    def padding() -> str:
        return ": " + " " * 2048 + "\n\n"


class SessionHandler:
    def __init__(self, workspace: str, model: str):
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.model = model
        self._status_queue = []  # Queue for status messages from callback

    def get_session(self):
        return SessionManager.get_or_create(self.workspace, self.model)

    def _status_callback(self, message: str):
        self._status_queue.append(message)

    def start_session(self, session, status_msg: str):
        yield SSEFormatter.send({'type': 'status', 'message': status_msg})
        session.start()
        yield SSEFormatter.send({'type': 'status', 'message': 'Initializing Augment...'})

        # Clear status queue
        self._status_queue = []

        # Start polling for prompt with status callback
        # We need to use threading to collect status messages while waiting
        import threading
        import queue

        status_q = queue.Queue()
        result_holder = {'success': False, 'output': ''}

        def callback(msg):
            status_q.put(msg)

        def wait_thread():
            success, output = session.wait_for_prompt(status_callback=callback)
            result_holder['success'] = success
            result_holder['output'] = output
            status_q.put(None)  # Signal completion

        # Start wait in background thread
        thread = threading.Thread(target=wait_thread, daemon=True)
        thread.start()

        # Yield status messages as they come
        while True:
            try:
                msg = status_q.get(timeout=0.5)
                if msg is None:
                    break  # Wait completed
                yield SSEFormatter.send({'type': 'status', 'message': msg})
            except queue.Empty:
                # No message yet, just continue waiting
                pass

        # Wait for thread to finish
        thread.join(timeout=5)

        if not result_holder['success']:
            session.cleanup()
            yield SSEFormatter.send({'type': 'error', 'message': 'Failed to start Augment'})
            return False

        session.initialized = True
        return True

    def send_message(self, session, message: str):
        try:
            # Drain leftover output (quick drain)
            drained = session.drain_output(timeout=0.1)
            if drained > 0:
                log.info(f"Drained {drained} bytes before sending")

            # Check if this is an image command (format: /images <path1> <path2> ... <question>)
            if message.startswith('/images '):
                return self._send_image_message(session, message)

            # Sanitize message for terminal (newlines → spaces, special chars → ASCII)
            sanitized_message = _sanitize_message(message)

            # Send message with carriage return - reduced delays for faster response
            os.write(session.master_fd, sanitized_message.encode('utf-8'))
            time.sleep(0.1)  # Reduced from 0.5s - minimal delay needed
            os.write(session.master_fd, b'\r')
            time.sleep(0.05)  # Reduced from 0.3s
            log.info(f"Message sent: {sanitized_message[:30]}...")
            return (True, message)
        except (BrokenPipeError, OSError) as e:
            log.error(f"Write error: {e}")
            session.cleanup()
            return (False, message)

    def _send_image_message(self, session, message: str):
        log.info(f"[IMAGE] ========== _send_image_message CALLED ==========")
        log.info(f"[IMAGE] Full message: {message[:100]}...")
        try:
            # Parse the message: /images <path>|||<question>
            parts = message[8:].strip()  # Remove '/images '

            # Split by ||| delimiter
            if '|||' in parts:
                image_path, question = parts.split('|||', 1)
                image_path = image_path.strip()
                question = question.strip()
            else:
                # Fallback: no delimiter, assume entire thing is path
                image_path = parts
                question = ''

            if not image_path:
                log.warning("No image path found in /images command, sending as regular message")
                success = self._send_regular_message(session, message)
                return (success, message)

            log.info(f"[IMAGE] Sending image: {image_path}")
            log.info(f"[IMAGE] Question: {question[:50] if question else '(none)'}...")

            # Step 1: Send /image command to enter image input mode
            # First type /image
            os.write(session.master_fd, b'/image')
            time.sleep(0.5)  # Wait for autocomplete to show
            # Press Enter to select the /image command
            os.write(session.master_fd, b'\r')
            time.sleep(2.0)  # Wait longer for auggie to switch to image mode (shows clip icon)
            # Drain output (just to clear buffer)
            drained1 = session.drain_output(timeout=0.5)
            log.info(f"[IMAGE] After /image command, drained {drained1} bytes")

            # Step 2: Send the image path
            log.info(f"[IMAGE] Now sending path: {image_path}")
            os.write(session.master_fd, image_path.encode('utf-8'))
            time.sleep(0.3)  # Small delay before Enter
            os.write(session.master_fd, b'\r')
            time.sleep(2.0)  # Wait longer for auggie to process and accept the image path
            # Drain output
            drained2 = session.drain_output(timeout=0.5)
            log.info(f"[IMAGE] After path, drained {drained2} bytes")

            # Step 3: Send the question
            if question:
                sanitized_question = _sanitize_message(question)
                os.write(session.master_fd, sanitized_question.encode('utf-8'))
                time.sleep(0.1)
                os.write(session.master_fd, b'\r')
                time.sleep(0.1)
                log.info(f"[IMAGE] Sent question: {sanitized_question[:50]}...")
            else:
                log.warning("[IMAGE] No question provided with image")

            # Return the question for echo detection (last thing sent to terminal)
            return (True, question if question else image_path)

        except (BrokenPipeError, OSError) as e:
            log.error(f"Write error during image send: {e}")
            session.cleanup()
            return (False, message)

    def _send_regular_message(self, session, message: str) -> bool:
        sanitized_message = _sanitize_message(message)
        os.write(session.master_fd, sanitized_message.encode('utf-8'))
        time.sleep(0.1)
        os.write(session.master_fd, b'\r')
        time.sleep(0.05)
        log.info(f"Message sent: {sanitized_message[:30]}...")
        return True


class StreamGenerator:
    # Timeout Configuration (in seconds)

    STREAM_TIMEOUT = 300          # Maximum total stream duration (5 minutes)
    RAW_BUFFER_MAX = 300_000      # Max bytes to buffer from PTY output

    # Silence detection timeouts (how long to wait with no new content)
    CONTENT_SILENCE_TIMEOUT = 5.0       # When content looks complete
    CONTENT_SILENCE_EXTENDED = 60.0     # When tools are executing (file ops, etc.)
    CONTENT_SILENCE_INCOMPLETE = 45.0   # When content looks truncated/incomplete
    END_PATTERN_SILENCE = 1.0           # After detecting end pattern (box UI)
    RESPONSE_MARKER_TIMEOUT = 5.0       # Data silence after response marker (●)
    WAIT_FOR_MARKER_TIMEOUT = 45.0      # Max wait for first response marker

    def __init__(self, message: str, workspace: str, chat_id: str = None):
        self.message = message
        self.workspace = workspace
        self.chat_id = chat_id
        self.message_id = None
        self.start_time = time.time()  # Track execution time for Slack
        # For image messages, store the last command sent (question) for echo detection
        self.echo_search_message = message

        # Initialize components - only create repository if history is enabled
        self.repository = ChatRepository(chat_id) if (chat_id and settings.history_enabled) else None
        self.session_handler = SessionHandler(workspace, settings.model)
        # Initialize processor with sanitized message since that's what's actually sent to terminal
        self.processor = StreamProcessor(_sanitize_message(message))
        self.sse = SSEFormatter()

    def generate(self):
        log.info(f"Starting generate for: {self.message[:50]}...")

        # Mark chat as streaming
        if self.repository:
            self.repository.set_streaming_status('streaming')

        try:
            yield self.sse.padding()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            log.warning(f"Client disconnected early (padding): {type(e).__name__}")
            self._continue_in_background()
            return

        try:
            yield from self._handle_session()
        except (BrokenPipeError, ConnectionResetError) as e:
            # Client disconnected - continue processing in background
            log.warning(f"Client disconnected during streaming: {type(e).__name__}")
            self._continue_in_background()
            return
        except OSError as e:
            # Check if it's a broken pipe variant
            if e.errno == 32:  # EPIPE - Broken pipe
                log.warning(f"Client disconnected (EPIPE): {e}")
                self._continue_in_background()
                return
            # Re-raise other OSErrors
            raise
        except Exception as e:
            log.error(f"Exception: {e}")
            # Mark streaming as failed
            if self.repository:
                self.repository.set_streaming_status(None)
            # Send Slack notification for error
            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message,
                content="",
                success=False,
                error=str(e),
                stopped=False,
                execution_time=execution_time
            )
            try:
                yield self.sse.send({'type': 'error', 'message': str(e)})
                yield self.sse.send({'type': 'done'})
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Client already disconnected, can't send error
                log.warning("Could not send error to client - already disconnected")
                return

    def _continue_in_background(self):
        if self.repository:
            self.repository.set_streaming_status('pending')
            log.info(f"[BACKGROUND] Marked chat {self.chat_id} as pending for resume")

    def _handle_session(self):
        session, is_new = self.session_handler.get_session()
        log.info(f"Session: is_new={is_new}, initialized={session.initialized}")

        with session.lock:
            # Mark session as in use (terminal open) to prevent cleanup during streaming
            session.in_use = True
            try:
                # Initialize or reconnect session if needed
                init_result = yield from self._ensure_session_ready(session, is_new)
                if not init_result:
                    yield self.sse.send({'type': 'done'})
                    return

                if not session.master_fd:
                    log.error("No master_fd available")
                    yield self.sse.send({'type': 'error', 'message': 'No connection available'})
                    yield self.sse.send({'type': 'done'})
                    return

                # Send message
                success, self.echo_search_message = self.session_handler.send_message(session, self.message)
                if not success:
                    yield self.sse.send({'type': 'error', 'message': 'Connection lost. Please try again.'})
                    yield self.sse.send({'type': 'done'})
                    return

                # Update processor's search pattern if message changed (for image commands)
                # Always use sanitized version since that's what's actually sent to terminal
                if self.echo_search_message != self.message:
                    self.processor.update_search_message(_sanitize_message(self.echo_search_message))

                # Save question to database
                if self.repository:
                    self.message_id = self.repository.save_question(self.message)

                # Stream response
                state = self._create_initial_state(session)
                # Don't send hardcoded status - let auggie's actual indicators flow through
                yield from self._stream_response(session, state)
            finally:
                # Clear in_use flag when streaming is complete (or on error)
                session.in_use = False

    def _ensure_session_ready(self, session, is_new: bool):
        if is_new or not session.initialized:
            log.info("Starting new session...")
            for item in self.session_handler.start_session(session, 'Starting Augment...'):
                if isinstance(item, str):
                    yield item
                elif not item:
                    log.info("Session start failed")
                    return False
        elif not session.is_alive():
            log.info("Session dead, reconnecting...")
            session.cleanup()
            for item in self.session_handler.start_session(session, 'Reconnecting to Augment...'):
                if isinstance(item, str):
                    yield item
                elif not item:
                    log.info("Reconnect failed")
                    return False
        else:
            session.drain_output()
        return True

    def _create_initial_state(self, session) -> StreamState:
        previous_response = getattr(session, 'last_response', '') or ''
        session.last_response = ""
        session.last_message = ""

        state = StreamState(prev_response=previous_response)
        return state

    def _stream_response(self, session, state: StreamState):
        fd = session.master_fd
        _log(f"Starting stream loop, fd={fd}")

        # Track last status update time to avoid spamming
        last_status_time = 0
        last_status_msg = ""

        while state.elapsed_since_message < self.STREAM_TIMEOUT:
            # Check for abort
            if _abort_flag.is_set():
                yield from self._handle_abort(session, state)
                return

            # Read from terminal with short timeout for responsiveness
            # Use 0.01s (10ms) for quick response while still being efficient
            ready = select.select([fd], [], [], 0.01)[0]

            if ready:
                # Read all available data in a loop for better throughput
                while True:
                    try:
                        # Use larger buffer (8KB) for efficiency
                        chunk = os.read(fd, 8192).decode('utf-8', errors='ignore')
                        if not chunk:
                            break
                        # New data arrived after an end-pattern signal; treat it as transient
                        if state.end_pattern_seen:
                            state.end_pattern_seen = False
                        state.all_output += chunk
                        if len(state.all_output) > self.RAW_BUFFER_MAX:
                            state.all_output = state.all_output[-self.RAW_BUFFER_MAX:]
                        # Incremental ANSI stripping to avoid reprocessing full buffer
                        combined = state._raw_tail + chunk
                        clean_combined = TextCleaner.strip_ansi(combined)
                        if state._clean_tail and clean_combined.startswith(state._clean_tail):
                            append_clean = clean_combined[len(state._clean_tail):]
                        else:
                            append_clean = clean_combined
                        if append_clean:
                            state.clean_output += append_clean
                        state._raw_tail = combined[-64:] if len(combined) > 64 else combined
                        state._clean_tail = TextCleaner.strip_ansi(state._raw_tail)
                        state.update_data_time()
                    except BlockingIOError:
                        break
                    except OSError:
                        break
                    # Check if more data is immediately available
                    if not select.select([fd], [], [], 0)[0]:
                        break

                # Process accumulated data
                yield from self._process_accumulated_data(state)

            # Send periodic status updates (moved outside else to update during data flow too)
            now = time.time()
            if now - last_status_time >= 0.3:  # Update every 0.3s for responsive activity indicators
                status_msg = self._get_current_status(state)
                if status_msg and status_msg != last_status_msg:
                    log.debug(f"[STATUS] {status_msg}")
                    yield self.sse.send({'type': 'status', 'message': status_msg})
                    last_status_msg = status_msg
                    state.update_activity(status_msg)
                last_status_time = now

            if not ready:
                # No data available - still process accumulated data to flush buffered content
                # This handles the 0.3s timeout for partial lines without newlines
                yield from self._process_accumulated_data(state)

                # Check exit conditions
                if self._should_exit(state):
                    session.drain_output(0.5)
                    break

        # Finalize response
        yield from self._finalize_response(session, state)

    def _get_current_status(self, state: StreamState) -> str:
        # Check for specific activity indicators in RAW terminal output (not clean_output)
        # Activity indicators appear in the terminal UI, not in the cleaned response text
        output_tail = state.all_output[-3000:] if len(state.all_output) > 3000 else state.all_output

        # Detect specific activities from terminal output
        activity_msg = self._detect_activity(output_tail)
        if activity_msg:
            return activity_msg

        # Only surface status lines emitted by auggie itself
        return None

    def _detect_activity(self, output: str) -> str | None:
        # Activity patterns to look for
        activity_patterns = [
            'Summarizing conversation history',
            'Processing response',
            'Sending request',
            'Receiving response',
            'Codebase search',
            'Executing tools',
            'Reading file',
            'Searching',
        ]

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        for line in reversed(lines):
            for pattern in activity_patterns:
                if pattern in line:
                    # Return the actual line (includes elapsed time like "(5s)")
                    # Remove ANSI escape codes
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    # Remove box drawing characters
                    clean_line = re.sub(r'[│╭╮╯╰─┌┐└┘├┤┬┴┼]', '', clean_line)
                    # Remove "esc to interrupt" text but keep elapsed time
                    # Handle formats like "(5s • esc to interrupt)" -> "(5s)"
                    clean_line = re.sub(r'\s*[•·\-–—]\s*esc to interrupt', '', clean_line, flags=re.IGNORECASE)
                    # Clean up any double parentheses
                    clean_line = re.sub(r'\(\)', '', clean_line)
                    # Transform "(5s)", "(5s.)", "(5s •)" to "5s" - remove parentheses, dot, and bullet
                    clean_line = re.sub(r'\((\d+)s\.?\s*[•·\-–—]?\s*\)', r'\1s', clean_line)
                    clean_line = clean_line.strip()
                    if clean_line:
                        return clean_line

        return None

    def _process_accumulated_data(self, state: StreamState):
        clean = state.clean_output

        # Check for message echo (only if not found yet)
        if not state.saw_message_echo:
            self._check_message_echo(clean, state)

        # If we found the echo and have a lot of leading buffer, drop it for performance
        if state.saw_message_echo and state.output_start_pos > 0 and len(clean) > 200000:
            clean = clean[state.output_start_pos:]
            state.clean_output = clean
            state.output_start_pos = 0

        # Process content if we've seen the message echo
        if state.saw_message_echo:
            yield from self._process_content(clean, state)

    def _check_message_echo(self, clean: str, state: StreamState) -> None:
        # Use echo_search_message (for image messages this is the question, not the /images command)
        # Sanitize it since that's what's actually sent to terminal
        sanitized = _sanitize_message(self.echo_search_message)

        # Try progressively shorter prefixes for more robust matching
        for prefix_len in [50, 30, 20, 15]:
            msg_prefix = sanitized[:prefix_len] if len(sanitized) > prefix_len else sanitized
            if msg_prefix in clean:
                msg_pos = clean.rfind(msg_prefix)
                state.mark_message_echo_found(msg_pos)
                log.info(f"Message echo found at position {msg_pos} (prefix_len={prefix_len})")
                return

        # Fallback: if we have significant output and time has passed, assume echo was missed
        # This prevents getting stuck waiting for echo that might be garbled by terminal
        if len(clean) > 1000 and state.elapsed_since_message > 5.0:
            log.warning(f"Message echo not found after 5s with {len(clean)} chars, proceeding anyway")
            state.mark_message_echo_found(0)  # Start from beginning
            return

        if not state._logged_no_echo and len(clean) > 500:
            log.info(f"Waiting for message echo: {repr(sanitized[:30])}")
            state._logged_no_echo = True

    def _process_content(self, clean: str, state: StreamState):
        # DEBUG: Log raw PTY output to understand parsing issues
        if not hasattr(state, '_debug_logged') and len(clean) > 500:
            log.debug(f"[DEBUG] Raw clean output (last 1000 chars): {repr(clean[-1000:])}")
            state._debug_logged = True

        content = self.processor.process_chunk(clean, state)

        if content and len(content) > state.streamed_length:
            # Strip previous response if present
            content = ContentCleaner.strip_previous_response(content, state.prev_response)
            if not content:
                return

            state.end_pattern_seen = False

            # Store the FULL content before streaming (important for content_looks_complete)
            # This includes partial last line that hasn't been streamed yet
            if content != state.current_full_content:
                state.update_content_time()
                state.current_full_content = content

            if not state.streaming_started:
                state.mark_streaming_started()
                log.info(f"Streaming started, content length={len(content)}")
                yield self.sse.send({'type': 'stream_start'})

            # Send delta (only complete lines are streamed, partial line is buffered)
            delta = state.update_streamed_content(content)
            if delta:
                yield self.sse.send({'type': 'stream', 'content': delta})

                # Save partial content periodically (every 5 seconds or significant content)
                if self.repository and self.message_id:
                    if not hasattr(state, '_last_partial_save') or time.time() - state._last_partial_save > 5:
                        self.repository.save_partial_answer(self.message_id, content)
                        state._last_partial_save = time.time()

        # Check for end pattern (uses state.current_full_content for content_looks_complete)
        if self.processor.check_end_pattern(clean, state):
            state.end_pattern_seen = True


    def _should_exit(self, state: StreamState) -> bool:
        # PRIMARY EXIT: End pattern detected (empty prompt = auggie ready for next input)
        # This is THE definitive signal that the response is complete
        if state.end_pattern_seen and state.elapsed_since_data > self.END_PATTERN_SILENCE:
            _log(f"Exit: end_pattern_seen (auggie ready for input)")
            return True

        # FALLBACK EXITS: Only used when end pattern detection might have failed
        # These should be generous to avoid cutting off responses

        # Tools executing - use very long timeout
        if state.is_tool_executing():
            if state.elapsed_since_content > self.CONTENT_SILENCE_EXTENDED:
                _log(f"Exit: tool execution, {state.elapsed_since_content:.1f}s extended silence")
                return True
            return False  # Keep waiting for tools

        # Response started but no end pattern yet - wait for signal
        if state.saw_response_marker:
            # If no new data for a while, end it (fallback for missed end pattern)
            if state.content_looks_complete() and state.elapsed_since_data > 1.5:
                _log(f"Exit: {state.elapsed_since_data:.1f}s data silence - content looks complete")
                return True
            if state.elapsed_since_data > 12.0:
                _log(f"Exit: {state.elapsed_since_data:.1f}s data silence - assuming complete (fallback)")
                return True

        # Timeout waiting for response marker (auggie hasn't started responding)
        if state.saw_message_echo and not state.saw_response_marker:
            wait_time = int(state.elapsed_since_message)
            if state.should_log_wait(wait_time) and wait_time % 10 == 0:
                log.info(f"Waiting for response marker... {wait_time}s elapsed, activity: {state.current_activity or 'none'}")

            # Extend timeout if there's recent activity (summarizing, processing, etc.)
            if state.has_recent_activity(timeout=120.0):
                # Activity detected - use extended timeout (2 minutes from last activity)
                if state.elapsed_since_activity > 120.0:
                    _log(f"Exit: timeout waiting for response marker (activity stale: {state.current_activity})")
                    return True
            elif state.elapsed_since_message > self.WAIT_FOR_MARKER_TIMEOUT:
                _log(f"Exit: timeout waiting for response marker (no activity)")
                return True

        return False

    def _handle_abort(self, session, state: StreamState):
        log.info("Abort signal received")
        state.aborted = True
        _abort_flag.clear()

        try:
            os.write(session.master_fd, b'\x03')  # Ctrl+C
            time.sleep(0.2)
            session.drain_output(timeout=0.5)
        except Exception as e:
            log.warning(f"Error during abort: {e}")

        # Send Slack notification for stopped request
        execution_time = time.time() - self.start_time
        notify_completion(
            question=self.message,
            content="",
            success=False,
            stopped=True,
            execution_time=execution_time
        )

        yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
        yield self.sse.send({'type': 'done'})

    def _finalize_response(self, session, state: StreamState):
        if state.aborted:
            return

        # Extract final content
        relevant_output = state.clean_output[state.output_start_pos:] if state.output_start_pos > 0 else state.clean_output

        # DEBUG: Log the relevant output to see what we're extracting from
        log.info(f"[DEBUG_FINAL] relevant_output length: {len(relevant_output)}")
        log.info(f"[DEBUG_FINAL] Last 500 chars: {repr(relevant_output[-500:])}")
        log.info(f"[DEBUG_FINAL] state.current_full_content: {repr(state.current_full_content[:300] if state.current_full_content else 'None')}")
        log.info(f"[DEBUG_FINAL] state.last_streamed_content: {repr(state.last_streamed_content[:300] if state.last_streamed_content else 'None')}")

        # Use sanitized message for extraction since that's what was actually sent to terminal
        sanitized_message = _sanitize_message(self.message)
        response_text = ResponseExtractor.extract_full(relevant_output, sanitized_message)
        log.info(f"[DEBUG_FINAL] Extracted response_text: {repr(response_text[:200] if response_text else 'None')}")

        # Use current_full_content (includes partial last line) over last_streamed_content
        # This ensures we don't lose content that was being buffered
        raw_content = state.current_full_content or state.last_streamed_content or response_text
        raw_content = ContentCleaner.strip_previous_response(raw_content, state.prev_response)

        # Clean the content
        final_content = ContentCleaner.clean_assistant_content(raw_content)
        final_content = ContentCleaner.strip_previous_response(final_content, state.prev_response)

        _log(f"Response complete - raw: {len(raw_content) if raw_content else 0}, cleaned: {len(final_content) if final_content else 0}")

        # Flush any remaining buffered content (incomplete lines)
        if state.streaming_started and final_content:
            remaining = state.flush_remaining_content(final_content)
            if remaining:
                yield self.sse.send({'type': 'stream', 'content': remaining})

        # Send stream end
        if state.streaming_started:
            yield self.sse.send({'type': 'stream_end', 'content': final_content})
        elif final_content:
            yield self.sse.send({'type': 'stream_start'})
            # Send complete lines at once for seamless appearance
            lines = final_content.split('\n')
            for line in lines:
                if line.strip():
                    yield self.sse.send({'type': 'stream', 'content': line + '\n'})
                    time.sleep(0.02)  # Small delay between lines
            yield self.sse.send({'type': 'stream_end', 'content': ''})

        # Update session state
        session.last_used = time.time()
        session.last_message = self.message
        session.last_response = final_content or ""
        SessionManager.cleanup_old()

        # Save to database and clear streaming status
        if self.repository:
            if final_content and self.message_id:
                self.repository.save_answer(self.message_id, final_content)
            self.repository.set_streaming_status(None)  # Clear streaming status

        # Send Slack notification for completed request
        execution_time = time.time() - self.start_time
        has_error = not final_content or "Couldn't extract response" in (final_content or "")
        notify_completion(
            question=self.message,
            content=final_content or "",
            success=not has_error,
            error="Couldn't extract response" if has_error else None,
            stopped=False,
            execution_time=execution_time
        )

        # Send final events
        _log("Sending done event")
        yield self.sse.send({
            'type': 'response',
            'message': final_content or "Couldn't extract response. Please try again.",
            'workspace': self.workspace
        })
        yield self.sse.send({'type': 'done'})


class OpenAIStreamGenerator:

    def __init__(self, message: str, chat_id: str = None, history: List[dict] = None):
        self.message = message
        self.chat_id = chat_id
        self.history = history or []
        self.start_time = time.time()
        self.repository = ChatRepository(chat_id) if (chat_id and settings.history_enabled) else None
        self.sse = SSEFormatter()
        self._provider = None

    def _get_provider(self) -> OpenAIChatProvider:
        if self._provider is None:
            middleware_settings = get_middleware_settings()
            if not middleware_settings.openai_api_key:
                raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in environment.")
            self._provider = OpenAIChatProvider(api_key=middleware_settings.openai_api_key)
        return self._provider

    SYSTEM_PROMPT = """You are a helpful AI assistant. Format responses using markdown:

**Structure:**
- Use ## for section headers (renders as h3)
- Use bullet points (-) for unordered lists
- Use numbered lists (1. 2. 3.) for sequential steps
- Keep paragraphs short with blank lines between them

**Code:**
- Use ```language for code blocks (python, javascript, bash, etc.)
- Use `backticks` for inline code, commands, filenames

**Emphasis:**
- Use **bold** for key terms and important info
- Use *italic* sparingly for emphasis

**Tables:** Use markdown tables for structured data comparison

Keep responses concise, well-organized, and easy to scan. Do not use more than two consecutive line breaks."""

    def _build_messages(self) -> List[ChatMessage]:
        messages = [ChatMessage(role=MessageRole.SYSTEM, content=self.SYSTEM_PROMPT)]
        for msg in self.history:
            role_str = msg.get('role', 'user')
            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.USER if role_str == 'user' else MessageRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=msg.get('content', '')))
        messages.append(ChatMessage(role=MessageRole.USER, content=self.message))
        return messages

    async def generate(self):
        model = settings.openai_model
        log.info(f"[OPENAI] Starting stream for model: {model}")

        if self.repository:
            self.repository.set_streaming_status('streaming')

        yield self.sse.padding()
        yield self.sse.send({'type': 'status', 'message': f'Connecting to OpenAI ({model})...'})
        yield self.sse.send({'type': 'stream_start'})

        full_content = ""
        try:
            provider = self._get_provider()
            messages = self._build_messages()

            async for chunk in provider.chat_stream(messages=messages, model=model):
                if _abort_flag.is_set():
                    log.info("[OPENAI] Abort signal received")
                    _abort_flag.clear()
                    if self.repository:
                        self.repository.set_streaming_status(None)
                    yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
                    yield self.sse.send({'type': 'done'})
                    return
                for choice in chunk.choices:
                    if choice.delta.content:
                        content = choice.delta.content
                        full_content += content
                        yield self.sse.send({'type': 'stream', 'content': content})
                    if choice.finish_reason:
                        log.info(f"[OPENAI] Stream finished: {choice.finish_reason}")

            if self.repository:
                message_id = self.repository.save_question(self.message)
                if message_id:
                    self.repository.save_answer(message_id, full_content)
                self.repository.set_streaming_status(None)

            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message,
                content=full_content,
                success=True,
                error=None,
                stopped=False,
                execution_time=execution_time
            )

            yield self.sse.send({'type': 'stream_end', 'content': full_content})
            yield self.sse.send({'type': 'response', 'message': full_content})
            yield self.sse.send({'type': 'done'})

        except Exception as e:
            log.error(f"[OPENAI] Streaming error: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message,
                content="",
                success=False,
                error=str(e),
                stopped=False,
                execution_time=execution_time
            )
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})


@chat_router.post('/api/chat/stream')
async def chat_stream(request: Request, data: ChatStreamRequest):
    _abort_flag.clear()

    message = data.message
    workspace = data.workspace or settings.workspace
    chat_id = data.chatId

    log.info(f"[REQUEST] POST /api/chat/stream | provider: {settings.ai_provider} | message: '{message[:100]}...'")

    if settings.ai_provider == 'openai':
        generator = OpenAIStreamGenerator(message, chat_id=chat_id, history=data.history)

        async def openai_stream():
            async for chunk in generator.generate():
                if await request.is_disconnected():
                    log.warning("[OPENAI] Client disconnected")
                    return
                yield chunk

        log.info("[RESPONSE] POST /api/chat/stream | Status: 200 | OpenAI SSE stream initiated")

        return StreamingResponse(
            openai_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )

    generator = StreamGenerator(message, os.path.expanduser(workspace), chat_id=chat_id)

    async def stream_generator():
        gen = generator.generate()
        try:
            for chunk in gen:
                if await request.is_disconnected():
                    log.warning("[STREAM] Client disconnected, calling cleanup")
                    generator._continue_in_background()
                    return
                yield chunk
        except GeneratorExit:
            log.warning("[STREAM] GeneratorExit caught, client disconnected")
            generator._continue_in_background()
        finally:
            try:
                gen.close()
            except:
                pass

    log.info("[RESPONSE] POST /api/chat/stream | Status: 200 | Auggie SSE stream initiated")

    return StreamingResponse(
        stream_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@chat_router.post('/api/chat/abort')
async def chat_abort():
    log.info("[REQUEST] POST /api/chat/abort")
    _abort_flag.set()
    response_data = {'status': 'ok', 'message': 'Abort signal sent'}
    log.info(f"[RESPONSE] POST /api/chat/abort | Status: 200 | {response_data}")
    return response_data


@chat_router.post('/api/chat/reset')
async def chat_reset(data: Optional[ChatResetRequest] = None):
    workspace = data.workspace if data and data.workspace else settings.workspace
    workspace = os.path.expanduser(workspace)

    log.info(f"[REQUEST] POST /api/chat/reset | workspace: '{workspace}'")

    reset_success = SessionManager.reset(workspace)

    if not reset_success:
        response_data = {'status': 'error', 'message': 'Cannot reset: terminal is currently in use'}
        log.info(f"[RESPONSE] POST /api/chat/reset | Status: 409 | {response_data}")
        return JSONResponse(content=response_data, status_code=409)

    response_data = {'status': 'ok', 'message': 'Session reset successfully'}
    log.info(f"[RESPONSE] POST /api/chat/reset | Status: 200 | {response_data}")
    return response_data
