import os
import time
import select
import logging

from backend.config import settings
from backend.session.auggie import SessionManager
from backend.utils.content_cleaner import ContentCleaner
from backend.models.stream_state import StreamState
from backend.services.stream_processor import StreamProcessor
from backend.services.bots.slack.notifier import notify_completion

from .base_generator import BaseStreamGenerator
from .utils import sanitize_message, chat_log, _abort_flag
from .session_handler import SessionHandler

log = logging.getLogger('chat')


class AuggieStreamGenerator(BaseStreamGenerator):
    CONTENT_SILENCE_INCOMPLETE = 45.0

    def __init__(self, message: str, workspace: str, chat_id: str = None):
        from backend.services.auggie.provider import AuggieProvider

        super().__init__(message, workspace, chat_id)
        self.workspace = workspace
        self.echo_search_message = message

        auggie_session_id = None
        has_messages = False
        if self.repository:
            auggie_session_id = self.repository.get_auggie_session_id()
            if auggie_session_id:
                log.info(f"Found existing Auggie session_id: {auggie_session_id}")
            chat = self.repository.get_chat()
            if chat:
                has_messages = len(chat.get('messages', [])) > 0
                log.info(f"Chat has_messages: {has_messages}")

        force_new_session = auggie_session_id is None and not has_messages
        log.info(f"force_new_session={force_new_session} (session_id={auggie_session_id}, has_messages={has_messages})")
        self.session_handler = SessionHandler(workspace, settings.model, auggie_session_id, force_new_session)
        self._auggie_session_id = auggie_session_id
        self.processor = StreamProcessor(sanitize_message(message))
        self.provider = AuggieProvider()

    def get_provider(self):
        return self.provider

    def generate(self):
        log.info(f"Starting generate for: {self.message[:50]}...")

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
            log.warning(f"Client disconnected during streaming: {type(e).__name__}")
            self._continue_in_background()
            return
        except OSError as e:
            if e.errno == 32:
                log.warning(f"Client disconnected (EPIPE): {e}")
                self._continue_in_background()
                return
            log.error(f"OS error during streaming: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message, content="", success=False,
                error=str(e), stopped=False, execution_time=execution_time
            )
            try:
                yield self.sse.send({'type': 'error', 'message': str(e)})
                yield self.sse.send({'type': 'done'})
            except (BrokenPipeError, ConnectionResetError, OSError):
                log.warning("Could not send OS error to client - already disconnected")
                return
        except Exception as e:
            log.error(f"Exception: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message, content="", success=False,
                error=str(e), stopped=False, execution_time=execution_time
            )
            try:
                yield self.sse.send({'type': 'error', 'message': str(e)})
                yield self.sse.send({'type': 'done'})
            except (BrokenPipeError, ConnectionResetError, OSError):
                log.warning("Could not send error to client - already disconnected")
                return

    def _continue_in_background(self):
        if self.repository:
            self.repository.set_streaming_status('pending')
            log.info(f"[BACKGROUND] Marked chat {self.chat_id} as pending for resume")
            if not self._auggie_session_id:
                self._detect_and_save_session_id()
                log.info(f"[BACKGROUND] Attempted to save session_id on disconnect")

    def _handle_session(self):
        session, is_new = self.session_handler.get_session()
        log.info(f"Session: is_new={is_new}, initialized={session.initialized}")

        with session.lock:
            session.in_use = True
            try:
                init_result = yield from self._ensure_session_ready(session, is_new)
                if not init_result:
                    yield self.sse.send({'type': 'done'})
                    return

                if not session.master_fd:
                    log.error("No master_fd available")
                    yield self.sse.send({'type': 'error', 'message': 'No connection available'})
                    yield self.sse.send({'type': 'done'})
                    return

                success, self.echo_search_message = self.session_handler.send_message(session, self.message)
                if not success:
                    yield self.sse.send({'type': 'error', 'message': 'Connection lost. Please try again.'})
                    yield self.sse.send({'type': 'done'})
                    return

                yield self.sse.send({'type': 'status', 'message': 'Processing...'})

                if self.echo_search_message != self.message:
                    self.processor.update_search_message(sanitize_message(self.echo_search_message))

                if self.repository:
                    self.message_id = self.repository.save_question(self.message)

                state = self._create_initial_state(session)
                yield from self._stream_response(session, state)
            finally:
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
            log.warning(f"Session dead (pid={session.process.pid if session.process else None}), reconnecting...")
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
        return StreamState(prev_response=previous_response)

    def _stream_response(self, session, state: StreamState):
        fd = session.master_fd
        chat_log(f"Starting stream loop, fd={fd}")

        last_status_time = 0
        last_status_msg = ""

        while state.elapsed_since_message < self.STREAM_TIMEOUT:
            if _abort_flag.is_set():
                yield from self._handle_abort(session, state)
                return

            ready = select.select([fd], [], [], 0.05)[0]

            if ready:
                self.read_chunks(fd, state)
                yield from self._process_accumulated_data(state)

            now = time.time()
            if now - last_status_time >= 0.3 and not state.end_pattern_seen:
                status_msg = self._get_current_status(state)
                if status_msg and status_msg != last_status_msg:
                    log.debug(f"[STATUS] {status_msg}")
                    yield self.sse.send({'type': 'status', 'message': status_msg})
                    last_status_msg = status_msg
                    state.update_activity(status_msg)
                last_status_time = now

            if not ready:
                yield from self._process_accumulated_data(state)

                if self._should_exit(state):
                    session.drain_output(0.5)
                    break

        yield from self._finalize_response(session, state)

    def _get_current_status(self, state: StreamState) -> str:
        output_tail = state.all_output[-3000:] if len(state.all_output) > 3000 else state.all_output
        return self.detect_activity(output_tail)

    def _process_accumulated_data(self, state: StreamState):
        clean = state.clean_output

        if not state.saw_message_echo:
            self._check_message_echo(clean, state)

        if state.saw_message_echo and state.output_start_pos > 0 and len(clean) > 200000:
            clean = clean[state.output_start_pos:]
            state.clean_output = clean
            state.output_start_pos = 0

        if state.saw_message_echo:
            yield from self._process_content(clean, state)

    def _check_message_echo(self, clean: str, state: StreamState) -> None:
        sanitized = sanitize_message(self.echo_search_message)

        for prefix_len in [50, 30, 20, 15]:
            msg_prefix = sanitized[:prefix_len] if len(sanitized) > prefix_len else sanitized
            if msg_prefix in clean:
                msg_pos = clean.rfind(msg_prefix)
                state.mark_message_echo_found(msg_pos)
                log.info(f"Message echo found at position {msg_pos} (prefix_len={prefix_len})")
                return

        if len(clean) > 1000 and state.elapsed_since_message > 5.0:
            log.warning(f"Message echo not found after 5s with {len(clean)} chars, proceeding anyway")
            state.mark_message_echo_found(0)
            return

        if not state._logged_no_echo and len(clean) > 500:
            log.info(f"Waiting for message echo: {repr(sanitized[:30])}")
            state._logged_no_echo = True

    def _process_content(self, clean: str, state: StreamState):
        if not hasattr(state, '_debug_logged') and len(clean) > 500:
            log.debug(f"[DEBUG] Raw clean output (last 1000 chars): {repr(clean[-1000:])}")
            state._debug_logged = True

        content = self.processor.process_chunk(clean, state)

        if content and len(content) > state.streamed_length:
            content = ContentCleaner.strip_previous_response(content, state.prev_response)
            if not content:
                return

            state.end_pattern_seen = False

            if content != state.current_full_content:
                state.update_content_time()
                state.current_full_content = content

            if not state.streaming_started:
                state.mark_streaming_started()
                log.info(f"Streaming started, content length={len(content)}")
                yield self.sse.send({'type': 'stream_start'})

            delta = state.update_streamed_content(content)
            if delta:
                yield self.sse.send({'type': 'stream', 'content': delta})

                if self.repository and self.message_id:
                    if not hasattr(state, '_last_partial_save') or time.time() - state._last_partial_save > 5:
                        self.repository.save_partial_answer(self.message_id, content)
                        state._last_partial_save = time.time()

        if self.processor.check_end_pattern(clean, state):
            state.end_pattern_seen = True

    def _should_exit(self, state: StreamState) -> bool:
        if state.end_pattern_seen and state.elapsed_since_data > self.END_PATTERN_SILENCE:
            chat_log(f"Exit: end_pattern_seen (auggie ready for input)")
            return True

        if state.saw_response_marker:
            if state.has_recent_activity(timeout=self.CONTENT_SILENCE_EXTENDED):
                return False

            if state.content_looks_complete() and state.elapsed_since_data > 1.5:
                chat_log(f"Exit: {state.elapsed_since_data:.1f}s data silence - content looks complete")
                return True
            if state.elapsed_since_data > 12.0:
                chat_log(f"Exit: {state.elapsed_since_data:.1f}s data silence - assuming complete (fallback)")
                return True

        if state.saw_message_echo and not state.saw_response_marker:
            wait_time = int(state.elapsed_since_message)
            if state.should_log_wait(wait_time) and wait_time % 10 == 0:
                log.info(f"Waiting for response marker... {wait_time}s elapsed, activity: {state.current_activity or 'none'}")

            if state.has_recent_activity(timeout=120.0):
                if state.elapsed_since_activity > 120.0:
                    chat_log(f"Exit: timeout waiting for response marker (activity stale: {state.current_activity})")
                    return True
            elif state.elapsed_since_message > self.WAIT_FOR_MARKER_TIMEOUT:
                chat_log(f"Exit: timeout waiting for response marker (no activity)")
                return True

        return False

    def _handle_abort(self, session, state: StreamState):
        log.info("Abort signal received")
        state.aborted = True
        self.handle_abort_signal(session.master_fd, session)

        if self.repository and not self._auggie_session_id:
            self._detect_and_save_session_id(session)

        yield from self.send_abort_response()

    def _finalize_response(self, session, state: StreamState):
        if state.aborted:
            return

        relevant_output = state.clean_output[state.output_start_pos:] if state.output_start_pos > 0 else state.clean_output

        log.info(f"[DEBUG_FINAL] relevant_output length: {len(relevant_output)}")
        log.info(f"[DEBUG_FINAL] Last 500 chars: {repr(relevant_output[-500:])}")

        sanitized_message = sanitize_message(self.message)
        response_text = self.extract_final_response(relevant_output, sanitized_message)

        raw_content = state.current_full_content or state.last_streamed_content or response_text
        final_content = self.clean_final_content(raw_content, state.prev_response)
        final_content = ContentCleaner.strip_previous_response(final_content, state.prev_response)

        chat_log(f"Response complete - raw: {len(raw_content) if raw_content else 0}, cleaned: {len(final_content) if final_content else 0}")

        yield from self.finalize_content(state, final_content)

        session.last_used = time.time()
        session.last_message = self.message
        session.last_response = final_content or ""
        SessionManager.cleanup_old()

        if not self._auggie_session_id and final_content and self.repository:
            self._detect_and_save_session_id(session)

        has_error = not final_content or "Couldn't extract response" in (final_content or "")
        self.save_and_notify(
            final_content,
            success=not has_error,
            error="Couldn't extract response" if has_error else None
        )

        chat_log("Sending done event")
        yield from self.send_final_response(final_content)

    def _detect_and_save_session_id(self, session=None):
        from backend.session.persistence import session_manager
        from backend.session.auggie import _sessions

        log.info(f"[DETECT_SESSION] Starting detection for workspace={self.workspace}")
        try:
            session_id = session_manager.get_session('auggie', self.workspace)
            log.info(f"[DETECT_SESSION] session_manager.get_session returned: {session_id}")
            if session_id:
                self.repository.save_auggie_session_id(session_id)
                self._auggie_session_id = session_id
                if session is None:
                    session = _sessions.get(self.workspace)
                if session:
                    session.session_id = session_id
                    log.info(f"[DETECT_SESSION] Updated in-memory session.session_id to: {session_id}")
                log.info(f"[DETECT_SESSION] Saved new Auggie session_id: {session_id}")
            else:
                log.warning(f"[DETECT_SESSION] No session found for workspace={self.workspace}")
        except Exception as e:
            log.warning(f"[DETECT_SESSION] Failed to detect Auggie session_id: {e}")
