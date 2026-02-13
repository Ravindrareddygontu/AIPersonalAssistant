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
            # Skip lines that are just prompt artifacts
            if line.strip().startswith('›'):
                break  # Stop at prompt - this is leftover from terminal
            if line.strip() == '│' or line.strip().startswith('│ ›'):
                break  # Stop at box/prompt characters
            # Skip lines that look like they contain previous messages
            if '│                                                                          │' in line:
                continue
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).rstrip()

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

    def _save_answer_to_db(self, answer_content):
        """Save the answer to an existing question in MongoDB."""
        if not self.chat_id or not self.message_id:
            return
        try:
            # Clean assistant content to remove terminal artifacts
            cleaned_content = self._clean_assistant_content(answer_content)

            chats_collection = get_chats_collection()
            chat = chats_collection.find_one({'id': self.chat_id})
            if not chat:
                log.warning(f"[DB] Chat {self.chat_id} not found, cannot save answer")
                return

            messages = chat.get('messages', [])
            messages = msg_svc.add_answer(messages, self.message_id, cleaned_content, raw_answer=answer_content)

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
        msg_short = self.message[:30] if len(self.message) > 30 else self.message
        pattern = r'›\s*' + re.escape(msg_short)
        matches = list(re.finditer(pattern, clean_output))
        if not matches:
            return None, state

        last_match = None
        for match in matches:
            lookahead = clean_output[match.end():match.end()+200]
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

        after_msg = clean_output[last_match.end():]
        lines = after_msg.split('\n')
        content = []
        in_resp = False

        for line in lines:
            s = line.strip()
            if not s and not in_resp:
                continue
            if BOX_CHARS_PATTERN.match(s):
                continue
            if s.startswith('│ ›') or s == '│':
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
                    os.write(session.master_fd, self.message.encode('utf-8'))
                    time.sleep(0.1)
                    os.write(session.master_fd, b'\r')
                    time.sleep(0.1)
                    os.write(session.master_fd, b'\n')
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

                state = {'all_output': '', 'last_data_time': time.time(), 'message_sent_time': time.time(),
                         'saw_message_echo': False, 'saw_response_marker': False, 'streaming_started': False,
                         'last_streamed_content': '', 'streamed_length': 0}
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
                        log.info(f"[STREAM] saw_message_echo=True, all_output length={len(state['all_output'])}")
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
                            after_response = clean[clean.rfind('●'):] if '●' in clean else clean[-500:]
                            end_prompt = _END_PATTERN_PROMPT.search(after_response)
                            end_box = _END_PATTERN_BOX.search(after_response[-300:] if len(after_response) > 300 else after_response)
                            if end_prompt or end_box:
                                state['end_pattern_seen'] = True
                                log.info(f"[STREAM] end_pattern_seen=True, streamed_length={state['streamed_length']}")
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
                    _log("Exiting: timeout waiting for response marker")
                    break

        response_text = ResponseExtractor.extract_full(state['all_output'], self.message)
        # Use the streamed content as primary, fall back to extracted response
        final_content = state['last_streamed_content'] or response_text
        _log(f"Response complete - length: {len(final_content) if final_content else 0}")

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
            self._save_answer_to_db(final_content)

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
