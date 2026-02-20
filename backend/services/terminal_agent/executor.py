import os
import time
import select
import logging
from typing import Optional, Dict, Tuple

from backend.services.terminal_agent.base import TerminalAgentProvider, TerminalAgentResponse
from backend.services.terminal_agent.session import TerminalSession
from backend.services.terminal_agent.processor import BaseStreamProcessor
from backend.models.stream_state import StreamState
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner

log = logging.getLogger('terminal_agent.executor')


class SessionManager:
    _sessions: Dict[str, TerminalSession] = {}

    @classmethod
    def get_or_create(
        cls,
        provider: TerminalAgentProvider,
        workspace: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[TerminalSession, bool]:
        key = f"{provider.name}:{workspace}:{model or 'default'}"
        if key in cls._sessions:
            session = cls._sessions[key]
            if session.is_alive():
                return session, False
            session.cleanup()

        session = TerminalSession(provider, workspace, model, session_id)
        cls._sessions[key] = session
        return session, True

    @classmethod
    def cleanup_all(cls) -> None:
        for session in cls._sessions.values():
            session.cleanup()
        cls._sessions.clear()


class TerminalAgentExecutor:

    def __init__(self, provider: TerminalAgentProvider):
        self.provider = provider
        self.config = provider.config

    def execute(self, message: str, workspace: str, model: Optional[str] = None) -> TerminalAgentResponse:
        start_time = time.time()
        workspace = os.path.expanduser(workspace)

        if not os.path.isdir(workspace):
            return TerminalAgentResponse(
                success=False,
                content="",
                error=f"Workspace not found: {workspace}"
            )

        try:
            session, is_new = SessionManager.get_or_create(self.provider, workspace, model)

            with session.lock:
                session.in_use = True
                try:
                    if is_new or not session.initialized:
                        if not session.start():
                            return TerminalAgentResponse(
                                success=False, content="",
                                error=f"Failed to start {self.provider.name} session"
                            )
                        ready, _ = session.wait_for_prompt(self.config.prompt_wait_timeout)
                        if not ready:
                            return TerminalAgentResponse(
                                success=False, content="",
                                error=f"Failed to initialize {self.provider.name} session"
                            )
                        session.initialized = True
                    elif not session.is_alive():
                        session.cleanup()
                        if not session.start():
                            return TerminalAgentResponse(
                                success=False, content="",
                                error=f"Failed to restart {self.provider.name} session"
                            )
                        ready, _ = session.wait_for_prompt(self.config.prompt_wait_timeout)
                        if not ready:
                            return TerminalAgentResponse(
                                success=False, content="",
                                error=f"Failed to reconnect {self.provider.name} session"
                            )
                        session.initialized = True

                    response = self._send_and_wait(session, message)
                    response.execution_time = time.time() - start_time
                    return response

                finally:
                    session.in_use = False

        except Exception as e:
            log.exception(f"Error executing message: {e}")
            return TerminalAgentResponse(
                success=False, content="", error=str(e),
                execution_time=time.time() - start_time
            )

    def _check_activity_indicator(self, clean_output: str, state: StreamState) -> bool:
        if not state.saw_response_marker:
            return False
        last_section = clean_output[-500:] if len(clean_output) > 500 else clean_output
        for indicator in self.provider.get_activity_indicators():
            if indicator in last_section:
                log.debug(f"[EXECUTOR] Activity indicator detected: {indicator}")
                return True
        return state.is_tool_executing()

    def _send_and_wait(self, session: TerminalSession, message: str) -> TerminalAgentResponse:
        session.drain_output(timeout=0.2)
        session.drain_output(timeout=0.2)

        sanitized = self.provider.sanitize_message(message)
        if not session.write(sanitized.encode('utf-8')):
            return TerminalAgentResponse(success=False, content="", error="Write error")

        time.sleep(0.1)
        if not session.write(b'\r'):
            return TerminalAgentResponse(success=False, content="", error="Write error")

        processor = BaseStreamProcessor(self.provider, sanitized)
        state = StreamState(
            prev_response=session.last_response or "",
            tool_patterns=self.provider.get_tool_executing_patterns()
        )

        fd = session.master_fd
        start_time = time.time()
        last_data_time = time.time()

        log.info(f"[EXECUTOR] Waiting for response to: {message[:50]}...")

        while True:
            elapsed = time.time() - start_time
            silence = time.time() - last_data_time

            if elapsed > self.config.max_execution_time:
                log.warning(f"[EXECUTOR] Max execution time reached ({elapsed:.1f}s)")
                break

            ready = select.select([fd], [], [], 0.1)[0]
            if ready:
                try:
                    chunk = os.read(fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        state.all_output += chunk
                        last_data_time = time.time()
                except (BlockingIOError, OSError):
                    pass

            if state.all_output:
                clean = TextCleaner.strip_ansi(state.all_output)

                if not state.saw_message_echo:
                    pos = processor.find_message_echo(clean, sanitized)
                    if pos >= 0:
                        state.mark_message_echo_found(pos)

                if state.saw_message_echo:
                    processor.process_chunk(clean, state)

                    if processor.check_end_pattern(clean, state):
                        log.info(f"[EXECUTOR] End pattern detected")
                        break

                    if self._check_activity_indicator(clean, state):
                        last_data_time = time.time()
                        continue

            if state.saw_response_marker and silence > self.config.silence_timeout:
                log.info(f"[EXECUTOR] Silence timeout after response ({silence:.1f}s)")
                break

        session.drain_output(0.3)
        clean_all = TextCleaner.strip_ansi(state.all_output)
        relevant = clean_all[state.output_start_pos:] if state.output_start_pos > 0 else clean_all

        markers = self.provider.get_response_markers()
        response_marker = markers[0] if markers else None
        response_text = ResponseExtractor.extract_full(
            relevant, sanitized,
            response_marker=response_marker,
            thinking_marker=self.provider.get_thinking_marker(),
            continuation_marker=self.provider.get_continuation_marker(),
        )

        content = state.current_full_content or state.last_streamed_content or ""
        if response_text and len(response_text) > len(content):
            content = response_text

        content = ContentCleaner.strip_previous_response(content, state.prev_response)
        final_content = ContentCleaner.clean_assistant_content(content)

        session.last_message = message
        session.last_response = final_content or ""

        if final_content:
            log.info(f"[EXECUTOR] Response complete: {len(final_content)} chars")
            return TerminalAgentResponse(success=True, content=final_content)
        else:
            return TerminalAgentResponse(
                success=False, content="", error="Could not extract response"
            )

