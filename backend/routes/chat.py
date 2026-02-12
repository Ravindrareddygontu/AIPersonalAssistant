import os
import re
import json
import time
import select
from flask import Blueprint, request, Response, stream_with_context
from backend.config import settings, SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.session import SessionManager
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor

chat_bp = Blueprint('chat', __name__)
_END_PATTERN_PROMPT = re.compile(r'│ ›\s*│')
_END_PATTERN_BOX = re.compile(r'╰─+╯')


class StreamGenerator:
    def __init__(self, message, workspace):
        self.message = message
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')

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
        yield ": " + " " * 2048 + "\n\n"
        try:
            session, is_new = SessionManager.get_or_create(self.workspace)
            with session.lock:
                if is_new or not session.initialized:
                    for item in self._start_session(session, 'Starting Augment...'):
                        if isinstance(item, str):
                            yield item
                        elif not item:
                            return
                elif not session.is_alive():
                    session.cleanup()
                    for item in self._start_session(session, 'Reconnecting to Augment...'):
                        if isinstance(item, str):
                            yield item
                        elif not item:
                            return
                else:
                    yield self._send({'type': 'status', 'message': 'Connecting...'})
                    session.drain_output()

                if not session.master_fd:
                    return

                yield self._send({'type': 'status', 'message': 'Sending your message...'})
                try:
                    os.write(session.master_fd, self.message.encode('utf-8'))
                    time.sleep(0.1)
                    os.write(session.master_fd, b'\r')
                    time.sleep(0.1)
                    os.write(session.master_fd, b'\n')
                except (BrokenPipeError, OSError):
                    session.cleanup()
                    yield self._send({'type': 'error', 'message': 'Connection lost. Please try again.'})
                    return

                state = {'all_output': '', 'last_data_time': time.time(), 'message_sent_time': time.time(),
                         'saw_message_echo': False, 'saw_response_marker': False, 'streaming_started': False,
                         'last_streamed_content': ''}
                yield self._send({'type': 'status', 'message': 'Waiting for AI response...'})

                for item in self._stream_response(session, state):
                    yield item
        except Exception as e:
            yield self._send({'type': 'error', 'message': str(e)})

    def _stream_response(self, session, state):
        fd = session.master_fd
        state['last_content_change'] = time.time()
        state['end_pattern_seen'] = False

        while time.time() - state['message_sent_time'] < 300:
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
                        yield self._send({'type': 'status', 'message': 'Processing your request...'})

                    if state['saw_message_echo']:
                        content, state = self._process_chunk(clean, state)
                        if content and len(content) > len(state['last_streamed_content']):
                            state['last_content_change'] = time.time()
                            state['end_pattern_seen'] = False
                            if not state['streaming_started']:
                                state['streaming_started'] = True
                                yield self._send({'type': 'stream_start'})
                            delta = content[len(state['last_streamed_content']):] if content.startswith(state['last_streamed_content']) else content
                            if delta.strip():
                                for c in delta:
                                    yield self._send({'type': 'stream', 'content': c})
                            state['last_streamed_content'] = content

                        if state['streaming_started'] and state['saw_response_marker']:
                            after_response = clean[clean.rfind('●'):] if '●' in clean else clean[-500:]
                            end_prompt = _END_PATTERN_PROMPT.search(after_response)
                            end_box = _END_PATTERN_BOX.search(after_response[-300:] if len(after_response) > 300 else after_response)
                            if end_prompt or end_box:
                                state['end_pattern_seen'] = True
                except OSError:
                    break
            else:
                elapsed_since_data = time.time() - state['last_data_time']
                elapsed_since_content = time.time() - state['last_content_change']

                if state['end_pattern_seen'] and elapsed_since_content > 1.0:
                    time.sleep(0.3)
                    session.drain_output(0.5)
                    break
                if state['saw_response_marker'] and elapsed_since_data > 5:
                    break
                if state['saw_message_echo'] and not state['saw_response_marker'] and time.time() - state['message_sent_time'] > 120:
                    break

        response_text = ResponseExtractor.extract_full(state['all_output'], self.message)
        if response_text and session.last_response:
            prev = session.last_response.strip()
            if response_text.startswith(prev):
                response_text = response_text[len(prev):].lstrip('\n')
            elif prev in response_text:
                response_text = response_text[response_text.find(prev) + len(prev):].lstrip('\n')

        final_content = response_text or state['last_streamed_content']

        if state['streaming_started']:
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

        yield self._send({'type': 'response', 'message': final_content or "Couldn't extract response. Please try again.", 'workspace': self.workspace})
        yield self._send({'type': 'done'})


@chat_bp.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.json
    gen = StreamGenerator(data.get('message', ''), os.path.expanduser(data.get('workspace', settings.workspace)))
    resp = Response(stream_with_context(gen.generate()), mimetype='text/event-stream')
    resp.headers.update({'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})
    return resp
