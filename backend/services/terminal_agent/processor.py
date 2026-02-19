import re
import logging
from typing import Optional, List, TYPE_CHECKING

from backend.models.stream_state import StreamState
from backend.utils.text import TextCleaner

if TYPE_CHECKING:
    from backend.services.terminal_agent.base import TerminalAgentProvider

log = logging.getLogger('terminal_agent.processor')


class BaseStreamProcessor:

    def __init__(self, provider: 'TerminalAgentProvider', user_message: str):
        self.provider = provider
        self.user_message = user_message
        self.message_short = user_message[:20] if len(user_message) > 20 else user_message

    def process_chunk(self, clean_output: str, state: StreamState) -> Optional[str]:
        search_output = clean_output[state.output_start_pos:]
        return self._extract_response_content(search_output, state)

    def _extract_response_content(self, after_msg: str, state: StreamState) -> Optional[str]:
        lines = after_msg.split('\n')
        content = []
        in_response = False
        response_markers = self.provider.get_response_markers()
        skip_patterns = self.provider.get_skip_patterns()

        for line in lines:
            stripped = line.strip()

            if not stripped and not in_response:
                continue

            for marker in response_markers:
                if stripped.startswith(marker):
                    in_response = True
                    state.mark_response_marker_seen()
                    c = stripped[len(marker):].strip()
                    if c:
                        content.append(c)
                    break
            else:
                if in_response and self._is_stop_condition(stripped):
                    break

                if any(skip in stripped for skip in skip_patterns):
                    continue

                if in_response and stripped:
                    content.append(stripped)

        return '\n'.join(content) if content else None

    def _is_stop_condition(self, stripped: str) -> bool:
        end_patterns = self.provider.get_end_patterns()
        for pattern in end_patterns:
            if pattern.search(stripped):
                return True
        return False

    def check_end_pattern(self, clean_output: str, state: StreamState) -> bool:
        if not state.streaming_started or not state.saw_response_marker:
            return False

        search_output = clean_output[state.output_start_pos:]
        last_section = search_output[-800:] if len(search_output) > 800 else search_output

        activity_indicators = self.provider.get_activity_indicators()
        for indicator in activity_indicators:
            if indicator in last_section:
                log.debug(f"[END_DETECT] Activity indicator found: {indicator}")
                return False

        end_patterns = self.provider.get_end_patterns()
        for pattern in end_patterns:
            if pattern.search(last_section):
                if state.has_substantial_content(min_length=10, min_time=1.0):
                    log.info(f"[END_DETECT] End pattern matched")
                    return True

        return False

    def find_message_echo(self, clean_output: str, sanitized_message: str) -> int:
        msg_prefix = sanitized_message[:30]
        pos = clean_output.rfind(msg_prefix)
        return pos if pos >= 0 else -1

