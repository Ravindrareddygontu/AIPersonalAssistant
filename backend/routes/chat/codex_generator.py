import os
import time
import select
import logging

from backend.services.bots.slack.notifier import notify_completion

from .base_generator import BaseStreamGenerator
from .utils import _abort_flag

log = logging.getLogger('chat')


class CodexStreamGenerator(BaseStreamGenerator):

    def __init__(self, provider_name: str, message: str, workspace: str, chat_id: str = None, model: str = None):
        from backend.services.terminal_agent.registry import TerminalAgentRegistry

        super().__init__(message, workspace, chat_id)
        self.provider = TerminalAgentRegistry.get(provider_name)
        if not self.provider:
            raise ValueError(f"Unknown terminal agent provider: {provider_name}")
        self.model = model

    def get_provider(self):
        return self.provider

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
        if self.provider.get_status_patterns():
            output_tail = state.all_output[-3000:] if len(state.all_output) > 3000 else state.all_output
            return self.detect_activity(output_tail)

        content = state.last_streamed_content or state.current_full_content
        if content:
            lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
            if lines:
                last_line = lines[-1][:80]
                if last_line and len(last_line) > 3:
                    return last_line
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
                state.aborted = True
                self.handle_abort_signal(fd, session)
                yield from self.send_abort_response()
                return

            ready = select.select([fd], [], [], 0.05)[0]
            if ready:
                if state.end_pattern_seen:
                    state.end_pattern_seen = False
                self.read_chunks(fd, state)

                clean = state.clean_output
                if not state.saw_message_echo:
                    pos = processor.find_message_echo(clean, sanitized_message)
                    if pos >= 0:
                        state.mark_message_echo_found(pos)
                    elif len(clean) > 1000 and state.elapsed_since_message > 5.0:
                        state.mark_message_echo_found(0)

                if state.saw_message_echo:
                    content = processor.process_chunk(clean, state)
                    yield from self.process_content_delta(state, content)
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

            if not ready and self.should_exit_streaming(state):
                break

        session.drain_output(0.5)
        yield from self._finalize_response(session, state, sanitized_message)

    def _finalize_response(self, session, state, sanitized_message: str):
        relevant = state.clean_output[state.output_start_pos:] if state.output_start_pos > 0 else state.clean_output
        response_text = self.extract_final_response(relevant, sanitized_message)

        raw_content = state.current_full_content or state.last_streamed_content or response_text
        final_content = self.clean_final_content(raw_content, state.prev_response)

        yield from self.finalize_content(state, final_content)

        session.last_message = self.message
        session.last_response = final_content or ""

        self.save_and_notify(
            final_content,
            success=bool(final_content),
            error=None if final_content else "Couldn't extract response"
        )

        yield from self.send_final_response(final_content)

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
