import os
import re
import json
import time
import select
import signal
import logging
import threading
from datetime import datetime
from flask import Blueprint, request, Response, stream_with_context, jsonify
from backend.config import settings, SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.session import SessionManager
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.database import get_chats_collection
from backend.services import message_service as msg_svc

log = logging.getLogger('chat')
chat_bp = Blueprint('chat', __name__)

def _log(msg):
    """Log to both logger and stdout for visibility"""
    log.info(msg)
    print(f"[CHAT] {msg}", flush=True)
_END_PATTERN_PROMPT = re.compile(r'│ ›\s*│')
_END_PATTERN_BOX = re.compile(r'╰─+╯')

# Global abort flag for current streaming request
_abort_flag = threading.Event()
_abort_lock = threading.Lock()


class StreamGenerator:
    def __init__(self, message, workspace, chat_id=None, message_id=None):
        self.message = message
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.chat_id = chat_id
        self.message_id = message_id  # Unique ID for this Q&A pair

    def _clean_assistant_content(self, content):
        """Remove terminal artifacts from assistant response before saving."""
        if not content:
            return content

        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Stop at prompt artifacts (marks end of AI response, start of prompt)
            if stripped.startswith('›'):
                break  # Stop at prompt - this is leftover from terminal
            if stripped == '│' or stripped.startswith('│ ›'):
                break  # Stop at box/prompt characters
            # Stop at lines that look like path prompts (e.g., "/home/user/project")
            if stripped.startswith('/') and ('/' in stripped[1:]) and len(stripped) < 100:
                # Likely a path like "/Projects/POC'S/ai-chat-app"
                break
            # Stop at lines that are terminal box tops (these mark UI boundaries)
            if stripped.startswith('╭') and '─' in stripped:
                break  # Box top boundary - we've reached terminal UI
            # Skip lines that look like terminal box/formatting
            if '│                                                                          │' in line:
                continue
            # Skip lines that are just box drawing characters
            if stripped and all(c in '─│╭╮╰╯┌┐└┘├┤┬┴┼' for c in stripped):
                continue
            # Skip lines that end with garbage numbers (terminal escape code remnants)
            if stripped and len(stripped) <= 5 and stripped.lstrip(';').isdigit():
                continue  # Skip garbage like ";139" or "39"
            # Clean trailing garbage characters (escape code remnants)
            if stripped.endswith(';') or (len(stripped) > 2 and stripped[-1].isdigit() and stripped[-2].isdigit() and stripped[-3] in ';│'):
                line = line.rstrip(';0123456789')
            cleaned_lines.append(line)

        result = '\n'.join(cleaned_lines).rstrip()
        # Final cleanup: remove trailing semicolons and numbers (common escape code artifacts)
        result = result.rstrip(';0123456789')
        return result

    def _save_question_to_db(self, question_content):
        """Save a new question to MongoDB and return the message ID."""
        if not self.chat_id:
            return None
        try:
            chats_collection = get_chats_collection()
            chat = chats_collection.find_one({'id': self.chat_id})
            if not chat:
                log.warning(f"[DB] Chat {self.chat_id} not found, cannot save question")
                return None

            messages = chat.get('messages', [])
            messages, msg_id = msg_svc.add_question(self.chat_id, messages, question_content)
            self.message_id = msg_id  # Store for later when saving answer

            # Update title if it's still "New Chat"
            title = chat.get('title', 'New Chat')
            if title == 'New Chat':
                title = question_content[:50] + ('...' if len(question_content) > 50 else '')

            chats_collection.update_one(
                {'id': self.chat_id},
                {'$set': {
                    'messages': messages,
                    'title': title,
                    'updated_at': datetime.utcnow().isoformat()
                }}
            )
            log.info(f"[DB] Saved question to chat {self.chat_id}, message_id: {msg_id}, total Q&A pairs: {len(messages)}")
            return msg_id
        except Exception as e:
            log.error(f"[DB] Failed to save question: {e}")
            return None

    def _save_answer_to_db(self, cleaned_content, raw_content=None):
        """Save the answer to an existing question in MongoDB."""
        if not self.chat_id or not self.message_id:
            return
        try:
            chats_collection = get_chats_collection()
            chat = chats_collection.find_one({'id': self.chat_id})
            if not chat:
                log.warning(f"[DB] Chat {self.chat_id} not found, cannot save answer")
                return

            messages = chat.get('messages', [])
            messages = msg_svc.add_answer(messages, self.message_id, cleaned_content, raw_answer=raw_content)

            chats_collection.update_one(
                {'id': self.chat_id},
                {'$set': {
                    'messages': messages,
                    'updated_at': datetime.utcnow().isoformat()
                }}
            )
            log.info(f"[DB] Saved answer to chat {self.chat_id}, message_id: {self.message_id}")
        except Exception as e:
            log.error(f"[DB] Failed to save answer: {e}")

    def _send(self, data):
        return f"data: {json.dumps(data)}\n\n"

    def _start_session(self, session, status_msg):
        yield self._send({'type': 'status', 'message': status_msg})
        session.start()
        yield self._send({'type': 'status', 'message': 'Waiting for Augment to initialize...'})
        if not session.wait_for_prompt()[0]:
            session.cleanup()
            yield self._send({'type': 'error', 'message': 'Failed to start Augment'})
            return False
        session.initialized = True
        return True

    def _process_chunk(self, clean_output, state):
        # CRITICAL FIX: Only search for the message echo in NEW output (after output_start_pos)
        # This prevents matching old message echoes from previous questions in the session
        search_start = state.get('output_start_pos', 0)
        search_output = clean_output[search_start:]

        msg_short = self.message[:30] if len(self.message) > 30 else self.message
        pattern = r'›\s*' + re.escape(msg_short)
        matches = list(re.finditer(pattern, search_output))
        if not matches:
            return None, state

        # Use the LAST match in the new output section (most recent echo of our message)
        last_match = None
        for match in matches:
            lookahead = search_output[match.end():match.end()+200]
            nl = lookahead.find('\n')
            first_line = lookahead[:nl] if nl > 0 else lookahead
            rest = lookahead[nl+1:] if nl > 0 else ""
            if '~' in lookahead or '●' in lookahead:
                last_match = match
            elif '│' not in first_line and '╰' not in first_line:
                if rest.strip() and '│ ›' not in rest[:100]:
                    last_match = match

        if not last_match:
            return None, state

        after_msg = search_output[last_match.end():]
        lines = after_msg.split('\n')
        content = []
        in_resp = False

        for line in lines:
            s = line.strip()
            if not s and not in_resp:
                continue
            if BOX_CHARS_PATTERN.match(s):
                continue
            # STOP CONDITIONS - marks end of AI response
            if s.startswith('│ ›') or s == '│':
                break
            # Stop at prompt lines (we've reached the input area)
            if s.startswith('›') and not s.startswith('›'):  # lone › is prompt
                break
            if '› ' in s and ('?' in s or 'files' in s.lower() or 'what' in s.lower()):
                # This looks like a previous question being echoed, stop
                break
            # Stop at path-like lines (terminal prompt showing current directory)
            if s.startswith('/') and '/' in s[1:] and len(s) < 100:
                break
            # Stop at lines that indicate queued messages
            if 'Message will be queued' in s:
                break
            if any(skip in s for skip in SKIP_PATTERNS):
                continue
            if s.startswith('~') or s.startswith('●'):
                in_resp = True
                state['saw_response_marker'] = True
                c = s[1:].strip()
                if c:
                    content.append(c)
            elif s.startswith('⎿') and in_resp:
                c = s[1:].strip()
                if c:
                    content.append(f"↳ {c}")
            elif in_resp and s:
                if not any(skip in s for skip in ['Claude Opus', 'Version 0.']):
                    content.append(s)

        return '\n'.join(content) if content else None, state

    def generate(self):
        log.info(f"[AUGMENT] Starting generate for message: {self.message[:50]}...")
        yield ": " + " " * 2048 + "\n\n"
        try:
            session, is_new = SessionManager.get_or_create(self.workspace)
            log.info(f"[AUGMENT] Session: is_new={is_new}, initialized={session.initialized}")
            with session.lock:
                if is_new or not session.initialized:
                    log.info("[AUGMENT] Starting new session...")
                    for item in self._start_session(session, 'Starting Augment...'):
                        if isinstance(item, str):
                            yield item
                        elif not item:
                            log.info("[AUGMENT] Session start failed, sending done")
                            yield self._send({'type': 'done'})
                            return
                elif not session.is_alive():
                    log.info("[AUGMENT] Session dead, reconnecting...")
                    session.cleanup()
                    for item in self._start_session(session, 'Reconnecting to Augment...'):
                        if isinstance(item, str):
                            yield item
                        elif not item:
                            log.info("[AUGMENT] Reconnect failed, sending done")
                            yield self._send({'type': 'done'})
                            return
                else:
                    yield self._send({'type': 'status', 'message': 'Connecting...'})
                    session.drain_output()

                if not session.master_fd:
                    log.error("[AUGMENT] No master_fd available")
                    yield self._send({'type': 'error', 'message': 'No connection available'})
                    yield self._send({'type': 'done'})
                    return

                log.info(f"[AUGMENT] Sending to auggie: {self.message[:30]}...")
                yield self._send({'type': 'status', 'message': 'Sending your message...'})
                try:
                    # For new sessions, give auggie extra time to fully initialize
                    if is_new or not session.initialized:
                        time.sleep(0.5)
                        session.drain_output(timeout=0.5)

                    # Send message first
                    os.write(session.master_fd, self.message.encode('utf-8'))
                    time.sleep(0.5)  # Increased delay to let TUI process the input
                    # Send just \r (carriage return) - this is what Enter sends in raw terminal mode
                    os.write(session.master_fd, b'\r')
                    time.sleep(0.3)
                    log.info(f"[AUGMENT] Message sent with CR, waiting for response...")
                except (BrokenPipeError, OSError) as e:
                    log.error(f"[AUGMENT] Write error: {e}")
                    session.cleanup()
                    yield self._send({'type': 'error', 'message': 'Connection lost. Please try again.'})
                    yield self._send({'type': 'done'})
                    return

                # Save user question to database (creates new Q&A pair)
                self._save_question_to_db(self.message)

                # Clear any cached response from previous messages
                session.last_response = ""
                session.last_message = ""

                # IMPORTANT: Track the output position BEFORE sending the message
                # This ensures we only look for responses in NEW output, not accumulated history
                state = {'all_output': '', 'last_data_time': time.time(), 'message_sent_time': time.time(),
                         'saw_message_echo': False, 'saw_response_marker': False, 'streaming_started': False,
                         'last_streamed_content': '', 'streamed_length': 0,
                         'output_start_pos': 0}  # Track where current message output starts
                yield self._send({'type': 'status', 'message': 'Waiting for AI response...'})

                for item in self._stream_response(session, state):
                    yield item
        except Exception as e:
            log.error(f"[AUGMENT] Exception: {e}")
            yield self._send({'type': 'error', 'message': str(e)})
            yield self._send({'type': 'done'})

    def _stream_response(self, session, state):
        fd = session.master_fd
        state['last_content_change'] = time.time()
        state['end_pattern_seen'] = False
        state['aborted'] = False
        _log(f"Starting stream_response loop, fd={fd}")

        while time.time() - state['message_sent_time'] < 300:
            # Check for abort signal
            if _abort_flag.is_set():
                log.info("[AUGMENT] Abort signal received, stopping stream")
                state['aborted'] = True
                _abort_flag.clear()
                # Send Ctrl+C to interrupt auggie
                try:
                    os.write(fd, b'\x03')  # Ctrl+C
                except:
                    pass
                break

            if select.select([fd], [], [], 0.005)[0]:
                try:
                    chunk = os.read(fd, 256).decode('utf-8', errors='ignore')
                    if not chunk:
                        continue
                    state['all_output'] += chunk
                    state['last_data_time'] = time.time()
                    clean = TextCleaner.strip_ansi(state['all_output'])

                    if not state['saw_message_echo'] and self.message in clean:
                        state['saw_message_echo'] = True
                        # CRITICAL FIX: Record the position where we found our message echo
                        # This ensures _process_chunk only looks at output AFTER this point
                        # preventing it from matching old responses from previous questions
                        msg_pos = clean.rfind(self.message)
                        state['output_start_pos'] = max(0, msg_pos - 50)  # Start slightly before message
                        log.info(f"[STREAM] saw_message_echo=True, all_output length={len(state['all_output'])}, output_start_pos={state['output_start_pos']}")

                    # Debug: Log raw output periodically to see what auggie is sending
                    if len(state['all_output']) % 500 < 256:  # Log every ~500 bytes
                        log.debug(f"[STREAM] Raw output sample (last 300 chars): {repr(clean[-300:])}")
                        yield self._send({'type': 'status', 'message': 'Processing your request...'})

                    if state['saw_message_echo']:
                        content, state = self._process_chunk(clean, state)
                        if content and len(content) > state['streamed_length']:
                            state['last_content_change'] = time.time()
                            state['end_pattern_seen'] = False
                            if not state['streaming_started']:
                                state['streaming_started'] = True
                                log.info(f"[STREAM] streaming_started=True, initial content length={len(content)}")
                                yield self._send({'type': 'stream_start'})

                            # Only send the new content (delta) - send as chunk, not char-by-char
                            delta = content[state['streamed_length']:]
                            if delta:
                                yield self._send({'type': 'stream', 'content': delta})
                                state['streamed_length'] = len(content)
                            state['last_streamed_content'] = content

                        if state['streaming_started'] and state['saw_response_marker']:
                            # CRITICAL FIX: Only look for end patterns in the NEW output section
                            search_start = state.get('output_start_pos', 0)
                            search_output = clean[search_start:]
                            after_response = search_output[search_output.rfind('●'):] if '●' in search_output else search_output[-500:]
                            end_prompt = _END_PATTERN_PROMPT.search(after_response)
                            end_box = _END_PATTERN_BOX.search(after_response[-300:] if len(after_response) > 300 else after_response)
                            # FIX: Require minimum content AND time elapsed before considering end pattern
                            # This prevents false end detection when terminal shows UI while AI is still working
                            # Real responses typically take > 5 seconds and have > 50 chars of actual content
                            time_since_start = time.time() - state['message_sent_time']
                            has_substantial_content = state['streamed_length'] > 50 and time_since_start > 5.0
                            # Also require the prompt pattern to be after a complete-looking response
                            # (not just a few lines showing "Read Directory" or "Terminal -")
                            last_content = state.get('last_streamed_content', '')
                            looks_complete = any(c in last_content for c in ['.', '!', ')', ']']) or len(last_content) > 200
                            if (end_prompt or end_box) and has_substantial_content and looks_complete:
                                state['end_pattern_seen'] = True
                                log.info(f"[STREAM] end_pattern_seen=True, streamed_length={state['streamed_length']}, time={time_since_start:.1f}s")
                except OSError:
                    break
            else:
                elapsed_since_data = time.time() - state['last_data_time']
                elapsed_since_content = time.time() - state['last_content_change']

                # Case 1: End pattern detected - wait 1 second of content silence then exit
                if state['end_pattern_seen'] and elapsed_since_content > 1.0:
                    _log(f"Exiting: end_pattern_seen and {elapsed_since_content:.1f}s content silence")
                    time.sleep(0.3)
                    session.drain_output(0.5)
                    break

                # Case 2: Streaming started and no content change for 3 seconds - likely done
                if state['streaming_started'] and elapsed_since_content > 3.0:
                    _log(f"Exiting: streaming_started and {elapsed_since_content:.1f}s content silence")
                    time.sleep(0.3)
                    session.drain_output(0.5)
                    break

                # Case 3: Response marker seen but no data for 5 seconds (fallback)
                if state['saw_response_marker'] and elapsed_since_data > 5:
                    _log(f"Exiting: saw_response_marker and {elapsed_since_data:.1f}s data silence")
                    break

                # Case 4: Very long wait without response marker - probably stuck (reduced from 120s to 30s)
                if state['saw_message_echo'] and not state['saw_response_marker'] and time.time() - state['message_sent_time'] > 30:
                    clean = TextCleaner.strip_ansi(state['all_output'])
                    _log(f"Exiting: timeout waiting for response marker. Total output: {len(state['all_output'])} bytes")
                    _log(f"[DEBUG] Last 500 chars of clean output: {repr(clean[-500:])}")
                    break

        # CRITICAL FIX: Only extract response from the NEW output section
        # This prevents extracting old responses from previous questions
        # NOTE: output_start_pos is calculated from CLEAN (ANSI-stripped) text,
        # so we must use clean text here too
        clean_all = TextCleaner.strip_ansi(state['all_output'])
        search_start = state.get('output_start_pos', 0)
        relevant_output = clean_all[search_start:] if search_start > 0 else clean_all
        response_text = ResponseExtractor.extract_full(relevant_output, self.message)
        # Use the streamed content as primary, fall back to extracted response
        raw_content = state['last_streamed_content'] or response_text
        log.info(f"[DEBUG] last_streamed_content length: {len(state['last_streamed_content']) if state['last_streamed_content'] else 0}")
        log.info(f"[DEBUG] response_text length: {len(response_text) if response_text else 0}")
        log.info(f"[DEBUG] raw_content first 200 chars: {repr(raw_content[:200]) if raw_content else 'None'}")
        # Clean the content to remove terminal artifacts and embedded previous answers
        final_content = self._clean_assistant_content(raw_content)
        _log(f"Response complete - raw length: {len(raw_content) if raw_content else 0}, cleaned length: {len(final_content) if final_content else 0}")
        log.info(f"[DEBUG] final_content first 200 chars: {repr(final_content[:200]) if final_content else 'None'}")

        if state['streaming_started']:
            _log("Sending stream_end event")
            yield self._send({'type': 'stream_end', 'content': final_content})
        elif final_content:
            yield self._send({'type': 'stream_start'})
            for i, w in enumerate(final_content.split(' ')):
                yield self._send({'type': 'stream', 'content': w + (' ' if i < len(final_content.split(' ')) - 1 else '')})
                time.sleep(0.02)
            yield self._send({'type': 'stream_end', 'content': ''})

        session.last_used = time.time()
        session.last_message = self.message
        session.last_response = final_content or ""
        SessionManager.cleanup_old()

        # Save assistant answer to the existing Q&A pair in database
        if final_content:
            self._save_answer_to_db(final_content, raw_content)

        _log("Sending 'done' event to frontend")
        yield self._send({'type': 'response', 'message': final_content or "Couldn't extract response. Please try again.", 'workspace': self.workspace})
        yield self._send({'type': 'done'})
        _log("Stream complete, all events sent")


@chat_bp.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    # Clear any previous abort flag
    _abort_flag.clear()
    data = request.json
    msg = data.get('message', '')
    ws = data.get('workspace', settings.workspace)
    chat_id = data.get('chatId')  # Frontend sends chatId for DB persistence
    log.info(f"[API] POST /api/chat/stream - message: {msg[:50]}{'...' if len(msg)>50 else ''}, workspace: {ws}, chatId: {chat_id}")
    gen = StreamGenerator(msg, os.path.expanduser(ws), chat_id=chat_id)
    resp = Response(stream_with_context(gen.generate()), mimetype='text/event-stream')
    resp.headers.update({'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})
    return resp


@chat_bp.route('/api/chat/abort', methods=['POST'])
def chat_abort():
    """Abort the current streaming request"""
    log.info("[API] POST /api/chat/abort - Setting abort flag")
    _abort_flag.set()
    return jsonify({'status': 'ok', 'message': 'Abort signal sent'})
