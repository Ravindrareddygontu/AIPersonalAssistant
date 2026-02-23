import os
import re
import time
import select
import logging
from abc import ABC, abstractmethod

from backend.config import settings
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner
from backend.models.stream_state import StreamState
from backend.services.chat_repository import ChatRepository
from backend.services.bots.slack.notifier import notify_completion

from .utils import SSEFormatter, _abort_flag

log = logging.getLogger('chat')


class BaseStreamGenerator(ABC):
    STREAM_TIMEOUT = 300
    RAW_BUFFER_MAX = 300_000
    CONTENT_SILENCE_TIMEOUT = 5.0
    CONTENT_SILENCE_EXTENDED = 60.0
    END_PATTERN_SILENCE = 1.0
    RESPONSE_MARKER_TIMEOUT = 5.0
    WAIT_FOR_MARKER_TIMEOUT = 45.0

    def __init__(self, message: str, workspace: str, chat_id: str = None):
        self.message = message
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.chat_id = chat_id
        self.message_id = None
        self.start_time = time.time()
        self.repository = ChatRepository(chat_id) if (chat_id and settings.history_enabled) else None
        self.sse = SSEFormatter()

    @abstractmethod
    def generate(self):
        pass

    @abstractmethod
    def get_provider(self):
        pass

    def read_chunks(self, fd, state: StreamState):
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

    def detect_activity(self, output: str) -> str | None:
        provider = self.get_provider()
        activity_patterns = provider.get_status_patterns()
        if not activity_patterns:
            return None

        clean_output = TextCleaner.strip_ansi(output)
        lines = [line.strip() for line in clean_output.splitlines() if line.strip()]
        for line in reversed(lines):
            line_lower = line.lower()
            for pattern in activity_patterns:
                if pattern.lower() in line_lower:
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    clean_line = re.sub(r'[│╭╮╯╰─┌┐└┘├┤┬┴┼]', '', clean_line)
                    clean_line = re.sub(r'\s*[•·\-–—]\s*esc to interrupt', '', clean_line, flags=re.IGNORECASE)
                    clean_line = re.sub(r'\((\d+)s\.?\s*[•·\-–—]?\s*\)', r'\1s', clean_line)
                    clean_line = re.sub(r'/queue\s+to\s+manage', '', clean_line, flags=re.IGNORECASE)
                    clean_line = re.sub(r'Message will be queued', '', clean_line, flags=re.IGNORECASE)
                    clean_line = re.sub(r'\(\s*\)', '', clean_line)
                    clean_line = clean_line.strip()
                    if clean_line:
                        return clean_line
        return None

    def should_exit_streaming(self, state: StreamState) -> bool:
        if state.end_pattern_seen and state.elapsed_since_data > self.END_PATTERN_SILENCE:
            return True

        if state.saw_response_marker:
            if state.has_recent_activity(timeout=self.CONTENT_SILENCE_EXTENDED):
                return False
            if state.content_looks_complete() and state.elapsed_since_data > 1.5:
                return True
            if state.elapsed_since_data > 12.0:
                return True

        if state.saw_message_echo and not state.saw_response_marker:
            if state.elapsed_since_message > self.WAIT_FOR_MARKER_TIMEOUT:
                return True

        return False

    def process_content_delta(self, content: str, state: StreamState, prev_response: str = ""):
        content = ContentCleaner.strip_previous_response(content, prev_response)
        if not content:
            return

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

    def finalize_content(self, state: StreamState, final_content: str):
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

    def extract_final_response(self, relevant_output: str, sanitized_message: str) -> str:
        provider = self.get_provider()
        markers = provider.get_response_markers()
        response_marker = markers[0] if markers else None
        return ResponseExtractor.extract_full(
            relevant_output, sanitized_message,
            response_marker=response_marker,
            thinking_marker=provider.get_thinking_marker(),
            continuation_marker=provider.get_continuation_marker(),
        )

    def clean_final_content(self, raw_content: str, prev_response: str = "") -> str:
        raw_content = ContentCleaner.strip_previous_response(raw_content, prev_response)
        return ContentCleaner.clean_assistant_content(raw_content)

    def save_and_notify(self, final_content: str, success: bool = True, stopped: bool = False, error: str = None):
        if self.repository:
            if final_content and self.message_id:
                self.repository.save_answer(self.message_id, final_content)
            self.repository.set_streaming_status(None)

        execution_time = time.time() - self.start_time
        notify_completion(
            question=self.message,
            content=final_content or "",
            success=success,
            error=error,
            stopped=stopped,
            execution_time=execution_time
        )

    def send_final_response(self, final_content: str):
        yield self.sse.send({
            'type': 'response',
            'message': final_content or "Couldn't extract response. Please try again.",
            'workspace': self.workspace
        })
        yield self.sse.send({'type': 'done'})

    def handle_abort_signal(self, fd, session=None):
        _abort_flag.clear()
        try:
            os.write(fd, b'\x03')
            time.sleep(0.2)
            if session:
                session.drain_output(timeout=0.5)
        except Exception as e:
            log.warning(f"Error during abort: {e}")

    def send_abort_response(self):
        self.save_and_notify("", success=False, stopped=True)
        yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
        yield self.sse.send({'type': 'done'})

