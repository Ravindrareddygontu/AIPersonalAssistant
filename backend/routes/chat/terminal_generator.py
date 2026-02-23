import os
import re
import time
import select
import logging

from backend.config import settings
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner
from backend.services.chat_repository import ChatRepository
from backend.services.bots.slack.notifier import notify_completion

from .utils import SSEFormatter, _abort_flag

log = logging.getLogger('chat')


class TerminalAgentStreamGenerator:
    STREAM_TIMEOUT = 300
    RAW_BUFFER_MAX = 300_000
    CONTENT_SILENCE_TIMEOUT = 5.0
    CONTENT_SILENCE_EXTENDED = 60.0
    END_PATTERN_SILENCE = 1.0
    RESPONSE_MARKER_TIMEOUT = 5.0
    WAIT_FOR_MARKER_TIMEOUT = 45.0

    def __init__(self, provider_name: str, message: str, workspace: str, chat_id: str = None, model: str = None):
        from backend.services.terminal_agent.registry import TerminalAgentRegistry
        self.provider = TerminalAgentRegistry.get(provider_name)
        if not self.provider:
            raise ValueError(f"Unknown terminal agent provider: {provider_name}")
        self.message = message
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.chat_id = chat_id
        self.model = model
        self.message_id = None
        self.start_time = time.time()
        self.repository = ChatRepository(chat_id) if (chat_id and settings.history_enabled) else None
        self.sse = SSEFormatter()

    def generate(self):
        from backend.services.codex.session import SessionManager as TASessionManager
        from backend.services.terminal_agent.processor import BaseStreamProcessor

        log.info(f"[{self.provider.name.upper()}] Starting stream for: {self.message[:50]}...")

        if self.repository:
            self.repository.set_streaming_status('streaming')

        try:
            yield self.sse.padding()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

        if self.provider.is_exec_mode:
            yield from self._generate_exec_mode()
            return

        try:
            session, is_new = TASessionManager.get_or_create(self.provider, self.workspace, self.model)

            with session.lock:
                session.in_use = True
                try:
                    if is_new or not session.initialized:
                        yield self.sse.send({'type': 'status', 'message': f'Starting {self.provider.name}...'})
                        if not session.start():
                            yield self.sse.send({'type': 'error', 'message': f'Failed to start {self.provider.name}'})
                            yield self.sse.send({'type': 'done'})
                            return
                        yield self.sse.send({'type': 'status', 'message': f'Initializing {self.provider.name}...'})
                        ready, _ = session.wait_for_prompt(self.provider.config.prompt_wait_timeout)
                        if not ready:
                            yield self.sse.send({'type': 'error', 'message': f'Failed to initialize {self.provider.name}'})
                            yield self.sse.send({'type': 'done'})
                            return
                        session.initialized = True
                    elif not session.is_alive():
                        yield self.sse.send({'type': 'status', 'message': f'Reconnecting to {self.provider.name}...'})
                        session.cleanup()
                        if not session.start():
                            yield self.sse.send({'type': 'error', 'message': f'Failed to restart {self.provider.name}'})
                            yield self.sse.send({'type': 'done'})
                            return
                        ready, _ = session.wait_for_prompt(self.provider.config.prompt_wait_timeout)
                        if not ready:
                            yield self.sse.send({'type': 'error', 'message': f'Failed to reconnect {self.provider.name}'})
                            yield self.sse.send({'type': 'done'})
                            return
                        session.initialized = True
                    else:
                        session.drain_output()

                    sanitized = self.provider.sanitize_message(self.message)
                    if not session.write(sanitized.encode('utf-8')):
                        yield self.sse.send({'type': 'error', 'message': 'Connection lost'})
                        yield self.sse.send({'type': 'done'})
                        return
                    time.sleep(0.1)
                    session.write(b'\r')
                    time.sleep(0.05)

                    yield self.sse.send({'type': 'status', 'message': 'Processing...'})

                    if self.repository:
                        self.message_id = self.repository.save_question(self.message)

                    yield from self._stream_response(session, sanitized, BaseStreamProcessor)

                finally:
                    session.in_use = False

        except Exception as e:
            log.exception(f"[{self.provider.name.upper()}] Exception: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            notify_completion(
                question=self.message, content="", success=False, error=str(e),
                stopped=False, execution_time=time.time() - self.start_time
            )
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})

    def _get_status_message(self, state) -> str | None:
        activity_patterns = self.provider.get_status_patterns()

        if activity_patterns:
            output_tail = state.all_output[-3000:] if len(state.all_output) > 3000 else state.all_output
            return self._detect_activity(output_tail)

        content = state.last_streamed_content or state.current_full_content
        if content:
            lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
            if lines:
                last_line = lines[-1][:80]
                if last_line and len(last_line) > 3:
                    return last_line
        return None

    def _detect_activity(self, output: str) -> str | None:
        activity_patterns = self.provider.get_status_patterns()
        if not activity_patterns:
            return None

        clean_output = TextCleaner.strip_ansi(output)
        lines = [line.strip() for line in clean_output.splitlines() if line.strip()]
        for line in reversed(lines):
            line_lower = line.lower()
            for pattern in activity_patterns:
                if pattern.lower() in line_lower:
                    clean_line = re.sub(r'[│╭╮╯╰─┌┐└┘├┤┬┴┼]', '', line)
                    clean_line = re.sub(r'\s*[•·\-–—]\s*esc to interrupt', '', clean_line, flags=re.IGNORECASE)
                    clean_line = re.sub(r'\(\)', '', clean_line)
                    clean_line = re.sub(r'\((\d+)s\.?\s*[•·\-–—]?\s*\)', r'\1s', clean_line)
                    clean_line = clean_line.strip()
                    if clean_line:
                        return clean_line
        return None

    def _stream_response(self, session, sanitized_message: str, ProcessorClass):
        from backend.models.stream_state import StreamState

        processor = ProcessorClass(self.provider, sanitized_message)
        state = StreamState(
            prev_response=session.last_response or "",
            tool_patterns=self.provider.get_tool_executing_patterns()
        )
        fd = session.master_fd
        last_status_time = time.time()
        last_status_msg = None

        log.info(f"[{self.provider.name.upper()}] Streaming response, fd={fd}")

        while state.elapsed_since_message < self.STREAM_TIMEOUT:
            if _abort_flag.is_set():
                _abort_flag.clear()
                state.aborted = True
                try:
                    os.write(fd, b'\x03')
                    session.drain_output(0.5)
                except Exception:
                    pass
                notify_completion(
                    question=self.message, content="", success=False,
                    stopped=True, execution_time=time.time() - self.start_time
                )
                yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
                yield self.sse.send({'type': 'done'})
                return

            ready = select.select([fd], [], [], 0.05)[0]
            if ready:
                while True:
                    try:
                        chunk = os.read(fd, 8192).decode('utf-8', errors='ignore')
                        if not chunk:
                            break
                        if state.end_pattern_seen:
                            state.end_pattern_seen = False
                        state.all_output += chunk
                        if len(state.all_output) > self.RAW_BUFFER_MAX:
                            state.all_output = state.all_output[-self.RAW_BUFFER_MAX:]
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
                    except (BlockingIOError, OSError):
                        break
                    if not select.select([fd], [], [], 0)[0]:
                        break

                clean = state.clean_output
                if not state.saw_message_echo:
                    pos = processor.find_message_echo(clean, sanitized_message)
                    if pos >= 0:
                        state.mark_message_echo_found(pos)
                    elif len(clean) > 1000 and state.elapsed_since_message > 5.0:
                        state.mark_message_echo_found(0)

                if state.saw_message_echo:
                    content = processor.process_chunk(clean, state)
                    if content and len(content) > state.streamed_length:
                        content = ContentCleaner.strip_previous_response(content, state.prev_response)
                        if content:
                            state.end_pattern_seen = False
                            if content != state.current_full_content:
                                state.update_content_time()
                                state.current_full_content = content
                            if not state.streaming_started:
                                state.mark_streaming_started()
                                yield self.sse.send({'type': 'stream_start'})
                            delta = state.update_streamed_content(content)
                            if delta:
                                yield self.sse.send({'type': 'stream', 'content': delta})
                    if processor.check_end_pattern(clean, state):
                        state.end_pattern_seen = True

            now = time.time()
            if now - last_status_time >= 0.3:
                status_msg = self._get_status_message(state)
                if status_msg and status_msg != last_status_msg:
                    log.debug(f"[STATUS] {status_msg}")
                    yield self.sse.send({'type': 'status', 'message': status_msg})
                    last_status_msg = status_msg
                    state.update_activity(status_msg)
                last_status_time = now

            if not ready:
                if state.end_pattern_seen and state.elapsed_since_data > self.END_PATTERN_SILENCE:
                    break
                if state.saw_response_marker:
                    if state.has_recent_activity(timeout=self.CONTENT_SILENCE_EXTENDED):
                        continue
                    if state.content_looks_complete() and state.elapsed_since_data > 1.5:
                        break
                    if state.elapsed_since_data > 12.0:
                        break
                if state.saw_message_echo and not state.saw_response_marker:
                    if state.elapsed_since_message > self.WAIT_FOR_MARKER_TIMEOUT:
                        break

        session.drain_output(0.5)
        clean_all = state.clean_output
        relevant = clean_all[state.output_start_pos:] if state.output_start_pos > 0 else clean_all
        markers = self.provider.get_response_markers()
        response_marker = markers[0] if markers else None
        response_text = ResponseExtractor.extract_full(
            relevant, sanitized_message,
            response_marker=response_marker,
            thinking_marker=self.provider.get_thinking_marker(),
            continuation_marker=self.provider.get_continuation_marker(),
        )

        raw_content = state.current_full_content or state.last_streamed_content or response_text
        raw_content = ContentCleaner.strip_previous_response(raw_content, state.prev_response)
        final_content = ContentCleaner.clean_assistant_content(raw_content)

        if state.streaming_started and final_content:
            remaining = state.flush_remaining_content(final_content)
            if remaining:
                yield self.sse.send({'type': 'stream', 'content': remaining})

        if state.streaming_started:
            yield self.sse.send({'type': 'stream_end', 'content': final_content})
        elif final_content:
            yield self.sse.send({'type': 'stream_start'})
            for line in final_content.split('\n'):
                if line.strip():
                    yield self.sse.send({'type': 'stream', 'content': line + '\n'})
                    time.sleep(0.02)
            yield self.sse.send({'type': 'stream_end', 'content': ''})

        session.last_message = self.message
        session.last_response = final_content or ""

        if self.repository:
            if final_content and self.message_id:
                self.repository.save_answer(self.message_id, final_content)
            self.repository.set_streaming_status(None)

        notify_completion(
            question=self.message, content=final_content or "", success=bool(final_content),
            error=None if final_content else "Couldn't extract response",
            stopped=False, execution_time=time.time() - self.start_time
        )

        yield self.sse.send({
            'type': 'response',
            'message': final_content or "Couldn't extract response. Please try again.",
            'workspace': self.workspace
        })
        yield self.sse.send({'type': 'done'})

    def _generate_exec_mode(self):
        import subprocess

        if self.provider.uses_json_output:
            yield from self._generate_exec_mode_json()
            return

        try:
            yield self.sse.send({'type': 'status', 'message': f'Running {self.provider.name}...'})

            if self.repository:
                self.message_id = self.repository.save_question(self.message)

            sanitized = self.provider.sanitize_message(self.message)
            cmd = self.provider.get_command(self.workspace, self.model, sanitized)
            env = self.provider.get_env()

            log.info(f"[{self.provider.name.upper()}] Exec command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.workspace,
                env=env,
                text=True,
                bufsize=1
            )

            yield self.sse.send({'type': 'stream_start'})

            full_output = []
            streaming_started = False
            in_response_section = False

            log.info(f"[{self.provider.name.upper()}] Reading output...")
            for line in iter(process.stdout.readline, ''):
                if _abort_flag.is_set():
                    _abort_flag.clear()
                    process.kill()
                    yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
                    yield self.sse.send({'type': 'done'})
                    return

                full_output.append(line)
                stripped = line.strip()
                log.debug(f"[{self.provider.name.upper()}] Line: {repr(stripped[:80] if len(stripped) > 80 else stripped)}, in_response: {in_response_section}")

                if stripped.startswith('codex'):
                    in_response_section = True
                    log.info(f"[{self.provider.name.upper()}] Started response section")
                    continue
                elif stripped.startswith(('thinking', 'exec', 'user', 'mcp ', 'tokens used', '--------', 'OpenAI Codex')):
                    in_response_section = False
                    continue
                elif stripped.startswith(('workdir:', 'model:', 'provider:', 'approval:', 'sandbox:', 'reasoning', 'session id:')):
                    continue

                if in_response_section and stripped:
                    streaming_started = True
                    log.info(f"[{self.provider.name.upper()}] Streaming: {stripped[:50]}")
                    yield self.sse.send({'type': 'stream', 'content': stripped + '\n'})

            process.wait()
            log.info(f"[{self.provider.name.upper()}] Process finished with code: {process.returncode}")

            final_content = self._extract_exec_response(''.join(full_output))

            if self.repository and final_content and self.message_id:
                self.repository.save_answer(self.message_id, final_content)
            if self.repository:
                self.repository.set_streaming_status(None)

            notify_completion(
                question=self.message, content=final_content or "", success=bool(final_content),
                error=None if final_content else "Couldn't extract response",
                stopped=False, execution_time=time.time() - self.start_time
            )

            yield self.sse.send({'type': 'stream_end', 'content': final_content or ''})
            yield self.sse.send({
                'type': 'response',
                'message': final_content or "Couldn't extract response. Please try again.",
                'workspace': self.workspace
            })
            yield self.sse.send({'type': 'done'})

        except Exception as e:
            log.exception(f"[{self.provider.name.upper()}] Exec mode exception: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            notify_completion(
                question=self.message, content="", success=False, error=str(e),
                stopped=False, execution_time=time.time() - self.start_time
            )
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})

    def _generate_exec_mode_json(self):
        import subprocess
        import json

        try:
            yield self.sse.send({'type': 'status', 'message': f'Running {self.provider.name}...'})

            if self.repository:
                self.message_id = self.repository.save_question(self.message)

            sanitized = self.provider.sanitize_message(self.message)
            cmd = self.provider.get_command(self.workspace, self.model, sanitized)
            env = self.provider.get_env()

            log.info(f"[{self.provider.name.upper()}] JSON exec command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace,
                env=env,
                text=True,
                bufsize=1
            )

            yield self.sse.send({'type': 'stream_start'})

            response_parts = []
            session_id = None
            if hasattr(self.provider, 'get_session_id'):
                session_id = self.provider.get_session_id(self.workspace, self.model)

            for line in iter(process.stdout.readline, ''):
                if _abort_flag.is_set():
                    _abort_flag.clear()
                    process.kill()
                    if session_id and hasattr(self.provider, 'store_session_id'):
                        self.provider.store_session_id(self.workspace, session_id, self.model)
                        log.info(f"[{self.provider.name.upper()}] Saved session_id on abort: {session_id}")
                    yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
                    yield self.sse.send({'type': 'done'})
                    return

                stripped = line.strip()
                if not stripped:
                    continue

                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug(f"[{self.provider.name.upper()}] Non-JSON line: {stripped[:80]}")
                    continue

                event_type = data.get('type', '')
                log.debug(f"[{self.provider.name.upper()}] JSON event: {event_type}")

                if event_type == 'thread.started':
                    new_session_id = data.get('thread_id')
                    if new_session_id and new_session_id != session_id:
                        session_id = new_session_id
                        if hasattr(self.provider, 'store_session_id'):
                            self.provider.store_session_id(self.workspace, session_id, self.model)

                elif event_type == 'turn.started':
                    yield self.sse.send({'type': 'status', 'message': 'Thinking...'})

                elif event_type == 'item.completed':
                    item = data.get('item', {})
                    item_type = item.get('type', '')
                    text = item.get('text', '')

                    if item_type == 'agent_message' and text:
                        response_parts.append(text)
                        yield self.sse.send({'type': 'stream', 'content': text + '\n'})
                    elif item_type == 'reasoning' and text:
                        status_text = text.replace('**', '').strip()[:100]
                        yield self.sse.send({'type': 'status', 'message': status_text})

                elif event_type == 'turn.completed':
                    log.info(f"[{self.provider.name.upper()}] Turn completed")

            process.wait()
            log.info(f"[{self.provider.name.upper()}] Process finished with code: {process.returncode}")

            final_content = '\n'.join(response_parts)

            if self.repository and final_content and self.message_id:
                self.repository.save_answer(self.message_id, final_content)
            if self.repository:
                self.repository.set_streaming_status(None)

            notify_completion(
                question=self.message, content=final_content or "", success=bool(final_content),
                error=None if final_content else "No response received",
                stopped=False, execution_time=time.time() - self.start_time
            )

            yield self.sse.send({'type': 'stream_end', 'content': final_content or ''})
            yield self.sse.send({
                'type': 'response',
                'message': final_content or "No response received. Please try again.",
                'workspace': self.workspace
            })
            yield self.sse.send({'type': 'done'})

        except Exception as e:
            log.exception(f"[{self.provider.name.upper()}] JSON exec mode exception: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            notify_completion(
                question=self.message, content="", success=False, error=str(e),
                stopped=False, execution_time=time.time() - self.start_time
            )
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})

    def _extract_exec_response(self, output: str) -> str:
        lines = output.split('\n')
        content = []
        in_codex_section = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('codex'):
                in_codex_section = True
                remainder = stripped[5:].strip()
                if remainder:
                    content.append(remainder)
                continue
            elif stripped.startswith(('thinking', 'exec', 'user', 'mcp ', 'tokens used', '--------')):
                in_codex_section = False
                continue

            if in_codex_section and stripped:
                content.append(stripped)

        return '\n'.join(content) if content else ''
