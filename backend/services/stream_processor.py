import re
import logging
from typing import Optional

from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.models.stream_state import StreamState

log = logging.getLogger('chat.stream')


class StreamProcessor:
    STATUS_LINE_RE = re.compile(r'\(\d+s\s*[•·]\s*esc to interrupt\)')
    END_PATTERN_PROMPT = re.compile(r'│ ›\s*│')
    END_PATTERN_BOX = re.compile(r'╰─+╯')
    EMPTY_PROMPT_PATTERN = re.compile(r'│ ›\s{20,}│')

    ACTIVITY_INDICATORS = [
        'Receiving response...',
        'Sending request...',
        'Processing response...',
        'Executing tools...',
        'Summarizing conversation history...',
        '▇▇▇',
    ]

    UI_SKIP_PATTERNS = ['Claude Opus', 'Version 0.', 'Message will be queued']

    def __init__(self, user_message: str):
        self.user_message = user_message
        self.message_short = user_message[:20] if len(user_message) > 20 else user_message
        self.message_pattern = re.compile(r'›\s*' + re.escape(self.message_short))
        self._message_history_pattern = self._build_message_history_pattern(user_message)

    def _build_message_history_pattern(self, message: str) -> Optional[re.Pattern]:
        message = message.strip()
        if len(message) < 5:
            return None
        return re.compile(r'^\d+\.\s+' + re.escape(message) + r'\s*$', re.IGNORECASE)

    def update_search_message(self, message: str):
        log.info(f"Updating search message to: {message[:30]}...")
        self.message_short = message[:20] if len(message) > 20 else message
        self.message_pattern = re.compile(r'›\s*' + re.escape(self.message_short))

    def process_chunk(self, clean_output: str, state: StreamState) -> Optional[str]:
        search_output = clean_output[state.output_start_pos:]
        return self._extract_response_content(search_output, state)

    def _extract_response_content(self, after_msg: str, state: StreamState) -> Optional[str]:
        lines = after_msg.split('\n')
        content = []
        in_response = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            if not stripped and not in_response:
                continue

            if BOX_CHARS_PATTERN.match(stripped):
                continue

            if stripped.startswith('●'):
                in_response = True
                state.mark_response_marker_seen()
                c = stripped[1:].strip()
                if c:
                    content.append(c)
                continue

            if stripped.startswith('~'):
                continue

            if stripped.startswith('⎿') and in_response:
                c = stripped[1:].strip()
                if c:
                    content.append(f"↳ {c}")
                continue

            if in_response and self._is_stop_condition(stripped):
                break

            if any(skip in stripped for skip in SKIP_PATTERNS):
                continue

            if self.STATUS_LINE_RE.search(stripped):
                continue

            if self._message_history_pattern and self._message_history_pattern.match(stripped):
                continue

            if in_response and stripped:
                if not any(skip in stripped for skip in self.UI_SKIP_PATTERNS):
                    content.append(stripped)

        return '\n'.join(content) if content else None

    def _is_stop_condition(self, stripped: str) -> bool:
        if 'Message will be queued' in stripped:
            return False

        if stripped.startswith('│ ›'):
            rest = stripped[3:].strip()
            return not rest or rest == '│'

        if stripped == '│':
            return True

        if stripped.startswith('›'):
            return True

        if '› ' in stripped and ('?' in stripped or 'files' in stripped.lower() or 'what' in stripped.lower()):
            return True

        if stripped.startswith('/') and '/' in stripped[1:] and len(stripped) < 100:
            if stripped.rstrip().endswith(('$', '%', '#', '>')):
                return True
            if len(stripped.split()) == 1:
                return True

        return False

    def _has_activity_indicator(self, text: str) -> bool:
        check_section = text[-500:] if len(text) > 500 else text
        return any(indicator in check_section for indicator in self.ACTIVITY_INDICATORS)

    def check_end_pattern(self, clean_output: str, state: StreamState) -> bool:
        if not state.streaming_started or not state.saw_response_marker:
            return False

        search_output = clean_output[state.output_start_pos:]
        last_section = search_output[-800:] if len(search_output) > 800 else search_output

        if self._has_activity_indicator(last_section):
            return False

        if not state.has_substantial_content(min_length=10, min_time=1.0):
            return False

        if self.EMPTY_PROMPT_PATTERN.search(last_section):
            if not getattr(state, '_end_detect_logged', False):
                log.info("Found empty input prompt - response complete")
                state._end_detect_logged = True
            return True

        end_section = last_section[-400:] if len(last_section) > 400 else last_section
        prompt_match = self.END_PATTERN_PROMPT.search(end_section)
        box_match = self.END_PATTERN_BOX.search(end_section)

        if prompt_match and box_match and box_match.start() >= prompt_match.start() - 50:
            if not getattr(state, '_end_detect_logged', False):
                log.info("Found prompt + box bottom sequence")
                state._end_detect_logged = True
            return True

        return False
