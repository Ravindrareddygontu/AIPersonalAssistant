import re
import logging
from typing import Optional

from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.utils.text import TextCleaner

log = logging.getLogger('response')

# =============================================================================
# Response Extraction Patterns
# =============================================================================

# Control characters (except newline, tab, carriage return) to strip
_CTRL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Section dividers: horizontal lines of 10+ box-drawing dashes
_SECTION_RE = re.compile(r'─{10,}')

# Status messages that indicate processing state, not actual content
_STATUS_PATTERNS = frozenset([
    'Sending request',
    'esc to interrupt',
    'Processing response',
    'Executing tools'
])


class ResponseExtractor:

    # Default markers (Auggie-style)
    DEFAULT_RESPONSE_MARKER = '●'
    DEFAULT_THINKING_MARKER = '~'
    DEFAULT_CONTINUATION_MARKER = '⎿'

    @staticmethod
    def extract_full(
        raw_output: str,
        user_message: str,
        response_marker: str = None,
        thinking_marker: str = None,
        continuation_marker: str = None,
    ) -> str:
        response_marker = response_marker or ResponseExtractor.DEFAULT_RESPONSE_MARKER
        thinking_marker = thinking_marker or ResponseExtractor.DEFAULT_THINKING_MARKER
        continuation_marker = continuation_marker or ResponseExtractor.DEFAULT_CONTINUATION_MARKER

        text = _CTRL_CHARS_RE.sub('', TextCleaner.strip_ansi(raw_output))

        msg_prefix = user_message[:30] if len(user_message) > 30 else user_message
        msg_pos = text.rfind(msg_prefix)

        if msg_pos < 0:
            log.debug(f"[EXTRACT] Message not found: {repr(msg_prefix[:20])}")
            return ""

        after_msg = text[msg_pos + len(msg_prefix):]
        marker_pos = after_msg.find(response_marker)

        if marker_pos < 0:
            log.debug(f"[EXTRACT] No {response_marker} marker found after message")
            return ""

        content_start = after_msg[marker_pos:]
        lines = []
        found = False

        for line in content_start.split('\n'):
            s = line.strip()
            if not s and not lines:
                continue

            if found and s.startswith('╭') and '─' in s:
                break
            if s.startswith('╰') and '─' in s:
                break
            if '│ ›' in s and s.endswith('│'):
                break

            if any(p in s for p in SKIP_PATTERNS):
                continue
            if any(p in s for p in _STATUS_PATTERNS):
                continue

            if s.startswith(thinking_marker):
                c = s[len(thinking_marker):].strip()
                if c:
                    lines.append(f"*{c}*")
            elif s.startswith(response_marker):
                found = True
                c = s[len(response_marker):].strip()
                if c:
                    lines.append(c)
            elif s.startswith(continuation_marker):
                c = s[len(continuation_marker):].strip()
                if c:
                    lines.append(f"  ↳ {c}")
            elif s and s[0] not in '╭╰' and not (s.startswith('│') and ('›' in s or len(s) < 5)) and not BOX_CHARS_PATTERN.match(s):
                if found:
                    lines.append(s)

        if lines and found:
            result = TextCleaner.clean_response('\n'.join(lines))
            if len(result.replace('\n', ' ').strip()) < 100 and any(p in result for p in _STATUS_PATTERNS):
                return ""
            return result

        return ""

