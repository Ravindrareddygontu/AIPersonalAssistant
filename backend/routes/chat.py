"""
Chat Routes - Handles chat streaming API endpoints.

Refactored following SOLID principles:
- Single Responsibility: Each class has one job
- Open/Closed: Easy to extend without modifying
- Dependency Injection: Dependencies are explicit
"""

import os
import json
import time
import select
import logging
import threading
from flask import Blueprint, request, Response, stream_with_context, jsonify

from backend.config import settings
from backend.session import SessionManager
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner
from backend.models.stream_state import StreamState
from backend.services.chat_repository import ChatRepository
from backend.services.stream_processor import StreamProcessor

log = logging.getLogger('chat')
chat_bp = Blueprint('chat', __name__)


def _sanitize_message(message: str) -> str:
    """
    Sanitize a message for terminal input.

    Replaces newlines with spaces and converts special Unicode characters
    that auggie uses for formatting (●, •, ⎿, etc.) to ASCII equivalents.
    This prevents confusion in response marker detection.
    """
    sanitized = message.replace('\n', ' ').replace('\r', ' ')
    return (sanitized
        .replace('●', '*')
        .replace('•', '-')
        .replace('⎿', '|')
        .replace('›', '>')
        .replace('╭', '+')
        .replace('╮', '+')
        .replace('╯', '+')
        .replace('╰', '+')
        .replace('│', '|')
        .replace('─', '-'))


# Global abort flag for current streaming request
_abort_flag = threading.Event()


def _log(msg: str) -> None:
    """Log to both logger and stdout for visibility."""
    log.info(msg)
    print(f"[CHAT] {msg}", flush=True)


class SSEFormatter:
    """Formats data for Server-Sent Events."""

    @staticmethod
    def send(data: dict) -> str:
        """Format data as SSE message."""
        return f"data: {json.dumps(data)}\n\n"

    @staticmethod
    def padding() -> str:
        """Initial padding for SSE stream."""
        return ": " + " " * 2048 + "\n\n"


class SessionHandler:
    """Handles Augment session lifecycle."""

    def __init__(self, workspace: str, model: str):
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.model = model

    def get_session(self):
        """Get or create a session, handling initialization."""
        return SessionManager.get_or_create(self.workspace, self.model)

    def start_session(self, session, status_msg: str):
        """Start a new session and wait for initialization."""
        yield SSEFormatter.send({'type': 'status', 'message': status_msg})
        session.start()
        yield SSEFormatter.send({'type': 'status', 'message': 'Waiting for Augment to initialize...'})

        if not session.wait_for_prompt()[0]:
            session.cleanup()
            yield SSEFormatter.send({'type': 'error', 'message': 'Failed to start Augment'})
            return False

        session.initialized = True
        return True

    def send_message(self, session, message: str) -> bool:
        """Send a message to the session."""
        try:
            # Drain leftover output (quick drain)
            drained = session.drain_output(timeout=0.1)
            if drained > 0:
                log.info(f"Drained {drained} bytes before sending")

            # Sanitize message for terminal (newlines → spaces, special chars → ASCII)
            sanitized_message = _sanitize_message(message)

            # Send message with carriage return - reduced delays for faster response
            os.write(session.master_fd, sanitized_message.encode('utf-8'))
            time.sleep(0.1)  # Reduced from 0.5s - minimal delay needed
            os.write(session.master_fd, b'\r')
            time.sleep(0.05)  # Reduced from 0.3s
            log.info(f"Message sent: {sanitized_message[:30]}...")
            return True
        except (BrokenPipeError, OSError) as e:
            log.error(f"Write error: {e}")
            session.cleanup()
            return False


class StreamGenerator:
    """Generates SSE stream for chat responses."""

    STREAM_TIMEOUT = 300  # 5 minutes max
    # Performance-tuned timeouts - balance speed vs tool execution
    CONTENT_SILENCE_TIMEOUT = 5.0  # Reduced from 15.0 - faster completion detection
    CONTENT_SILENCE_EXTENDED = 30.0  # Extended timeout when tools are executing
    END_PATTERN_SILENCE = 0.5  # Reduced from 1.0 - faster end detection
    RESPONSE_MARKER_TIMEOUT = 5.0  # Reduced from 10.0
    WAIT_FOR_MARKER_TIMEOUT = 45.0  # Reduced from 60.0

    def __init__(self, message: str, workspace: str, chat_id: str = None):
        self.message = message
        self.workspace = workspace
        self.chat_id = chat_id
        self.message_id = None

        # Initialize components
        self.repository = ChatRepository(chat_id) if chat_id else None
        self.session_handler = SessionHandler(workspace, settings.model)
        self.processor = StreamProcessor(message)
        self.sse = SSEFormatter()

    def generate(self):
        """Main generator for SSE stream."""
        log.info(f"Starting generate for: {self.message[:50]}...")
        yield self.sse.padding()

        try:
            yield from self._handle_session()
        except Exception as e:
            log.error(f"Exception: {e}")
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})

    def _handle_session(self):
        """Handle session setup and message sending."""
        session, is_new = self.session_handler.get_session()
        log.info(f"Session: is_new={is_new}, initialized={session.initialized}")

        with session.lock:
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
            yield self.sse.send({'type': 'status', 'message': 'Sending your message...'})
            if not self.session_handler.send_message(session, self.message):
                yield self.sse.send({'type': 'error', 'message': 'Connection lost. Please try again.'})
                yield self.sse.send({'type': 'done'})
                return

            # Save question to database
            if self.repository:
                self.message_id = self.repository.save_question(self.message)

            # Stream response
            state = self._create_initial_state(session)
            yield self.sse.send({'type': 'status', 'message': 'Waiting for AI response...'})
            yield from self._stream_response(session, state)

    def _ensure_session_ready(self, session, is_new: bool):
        """Ensure session is ready for use."""
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
            yield self.sse.send({'type': 'status', 'message': 'Connecting...'})
            session.drain_output()
        return True

    def _create_initial_state(self, session) -> StreamState:
        """Create initial stream state."""
        previous_response = getattr(session, 'last_response', '') or ''
        session.last_response = ""
        session.last_message = ""

        state = StreamState(prev_response=previous_response)
        return state

    def _stream_response(self, session, state: StreamState):
        """Stream the response from Augment."""
        fd = session.master_fd
        _log(f"Starting stream loop, fd={fd}")

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
                        state.all_output += chunk
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
            else:
                # No data available, check exit conditions
                if self._should_exit(state):
                    session.drain_output(0.5)
                    break

        # Finalize response
        yield from self._finalize_response(session, state)

    def _process_accumulated_data(self, state: StreamState):
        """Process accumulated data from terminal buffer."""
        output_len = len(state.all_output)

        # Only strip ANSI when we have new data (expensive operation)
        if hasattr(state, '_cached_clean_len') and state._cached_clean_len == output_len:
            clean = state._cached_clean
        else:
            clean = TextCleaner.strip_ansi(state.all_output)
            state._cached_clean = clean
            state._cached_clean_len = output_len

        # Check for message echo (only if not found yet)
        if not state.saw_message_echo:
            self._check_message_echo(clean, state)

        # Process content if we've seen the message echo
        if state.saw_message_echo:
            yield from self._process_content(clean, state)

    def _check_message_echo(self, clean: str, state: StreamState) -> None:
        """Check if we've seen the message echo in output."""
        # Use sanitized message (same sanitization as send_message) since that's what's sent to terminal
        sanitized = _sanitize_message(self.message)
        msg_prefix = sanitized[:50] if len(sanitized) > 50 else sanitized
        if msg_prefix in clean:
            msg_pos = clean.rfind(msg_prefix)
            state.mark_message_echo_found(msg_pos)
            log.info(f"Message echo found at position {msg_pos}")
        elif not state._logged_no_echo and len(clean) > 500:
            log.info(f"Waiting for message echo: {repr(msg_prefix[:30])}")
            state._logged_no_echo = True

    def _process_content(self, clean: str, state: StreamState):
        """Process and stream content."""
        content = self.processor.process_chunk(clean, state)

        if content and len(content) > state.streamed_length:
            # Strip previous response if present
            content = ContentCleaner.strip_previous_response(content, state.prev_response)
            if not content:
                return

            state.update_content_time()
            state.end_pattern_seen = False

            if not state.streaming_started:
                state.mark_streaming_started()
                log.info(f"Streaming started, content length={len(content)}")
                yield self.sse.send({'type': 'stream_start'})

            # Send delta
            delta = state.update_streamed_content(content)
            if delta:
                yield self.sse.send({'type': 'stream', 'content': delta})

        # Check for end pattern
        if self.processor.check_end_pattern(clean, state):
            state.end_pattern_seen = True


    def _should_exit(self, state: StreamState) -> bool:
        """Check if we should exit the stream loop."""
        # End pattern detected with content silence (fast path)
        if state.end_pattern_seen and state.elapsed_since_content > self.END_PATTERN_SILENCE:
            _log(f"Exit: end_pattern_seen, {state.elapsed_since_content:.1f}s silence")
            return True

        # Streaming started with content silence - adaptive timeout
        if state.streaming_started and state.elapsed_since_content > self.CONTENT_SILENCE_TIMEOUT:
            # Check if content looks complete for fast exit
            if state.content_looks_complete():
                _log(f"Exit: streaming_started, {state.elapsed_since_content:.1f}s silence, content complete")
                return True
            # Check if tools are executing - use extended timeout
            elif state.is_tool_executing():
                if state.elapsed_since_content > self.CONTENT_SILENCE_EXTENDED:
                    _log(f"Exit: streaming_started, {state.elapsed_since_content:.1f}s extended silence (tools)")
                    return True
            else:
                # No tools, content incomplete but give it a bit more time
                if state.elapsed_since_content > self.CONTENT_SILENCE_TIMEOUT * 2:
                    _log(f"Exit: streaming_started, {state.elapsed_since_content:.1f}s silence")
                    return True

        # Response marker seen but no data - reduced timeout
        if state.saw_response_marker and state.elapsed_since_data > self.RESPONSE_MARKER_TIMEOUT:
            _log(f"Exit: saw_response_marker, {state.elapsed_since_data:.1f}s data silence")
            return True

        # Timeout waiting for response marker
        if state.saw_message_echo and not state.saw_response_marker:
            wait_time = int(state.elapsed_since_message)
            if state.should_log_wait(wait_time) and wait_time % 10 == 0:
                log.info(f"Waiting for response marker... {wait_time}s elapsed")

            if state.elapsed_since_message > self.WAIT_FOR_MARKER_TIMEOUT:
                _log(f"Exit: timeout waiting for response marker")
                return True

        return False

    def _handle_abort(self, session, state: StreamState):
        """Handle abort signal."""
        log.info("Abort signal received")
        state.aborted = True
        _abort_flag.clear()

        try:
            os.write(session.master_fd, b'\x03')  # Ctrl+C
            time.sleep(0.2)
            session.drain_output(timeout=0.5)
        except Exception as e:
            log.warning(f"Error during abort: {e}")

        yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
        yield self.sse.send({'type': 'done'})

    def _finalize_response(self, session, state: StreamState):
        """Finalize and send the complete response."""
        if state.aborted:
            return

        # Extract final content
        clean_all = TextCleaner.strip_ansi(state.all_output)
        relevant_output = clean_all[state.output_start_pos:] if state.output_start_pos > 0 else clean_all
        response_text = ResponseExtractor.extract_full(relevant_output, self.message)

        raw_content = state.last_streamed_content or response_text
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

        # Save to database
        if final_content and self.repository and self.message_id:
            self.repository.save_answer(self.message_id, final_content, raw_content)

        # Send final events
        _log("Sending done event")
        yield self.sse.send({
            'type': 'response',
            'message': final_content or "Couldn't extract response. Please try again.",
            'workspace': self.workspace
        })
        yield self.sse.send({'type': 'done'})


# =============================================================================
# Flask Routes
# =============================================================================

@chat_bp.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """Stream chat response endpoint."""
    _abort_flag.clear()

    data = request.json
    message = data.get('message', '')
    workspace = data.get('workspace', settings.workspace)
    chat_id = data.get('chatId')

    log.info(f"[REQUEST] POST /api/chat/stream | message: '{message[:100]}...' | workspace: '{workspace}'")

    generator = StreamGenerator(message, os.path.expanduser(workspace), chat_id=chat_id)
    response = Response(
        stream_with_context(generator.generate()),
        mimetype='text/event-stream'
    )
    response.headers.update({
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    })

    log.info("[RESPONSE] POST /api/chat/stream | Status: 200 | SSE stream initiated")
    return response


@chat_bp.route('/api/chat/abort', methods=['POST'])
def chat_abort():
    """Abort current streaming request."""
    log.info("[REQUEST] POST /api/chat/abort")
    _abort_flag.set()
    response_data = {'status': 'ok', 'message': 'Abort signal sent'}
    log.info(f"[RESPONSE] POST /api/chat/abort | Status: 200 | {response_data}")
    return jsonify(response_data)


@chat_bp.route('/api/chat/reset', methods=['POST'])
def chat_reset():
    """Reset the auggie session for the current workspace."""
    data = request.json or {}
    workspace = data.get('workspace', settings.workspace)
    workspace = os.path.expanduser(workspace)

    log.info(f"[REQUEST] POST /api/chat/reset | workspace: '{workspace}'")

    SessionManager.reset(workspace)

    response_data = {'status': 'ok', 'message': 'Session reset successfully'}
    log.info(f"[RESPONSE] POST /api/chat/reset | Status: 200 | {response_data}")
    return jsonify(response_data)

