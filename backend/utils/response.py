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

    RESPONSE_MARKER = '●'
    THINKING_MARKER = '~'      # Thinking/reasoning text marker
    CONTINUATION_MARKER = '⎿'  # Continuation/sub-response marker

    @staticmethod
    def extract_full(raw_output: str, user_message: str) -> str:
        text = _CTRL_CHARS_RE.sub('', TextCleaner.strip_ansi(raw_output))

        # Find user message position (use shorter prefix for robustness)
        msg_prefix = user_message[:30] if len(user_message) > 30 else user_message
        msg_pos = text.rfind(msg_prefix)

        if msg_pos < 0:
            log.debug(f"[EXTRACT] Message not found: {repr(msg_prefix[:20])}")
            return ""

        # Look for ● marker AFTER the message
        after_msg = text[msg_pos + len(msg_prefix):]
        marker_pos = after_msg.find('●')

        if marker_pos < 0:
            log.debug(f"[EXTRACT] No ● marker found after message")
            return ""

        # Extract content starting from the marker
        content_start = after_msg[marker_pos:]
        lines = []
        found = False

        for line in content_start.split('\n'):
            s = line.strip()
            if not s and not lines:
                continue

            # Stop at UI box elements (new input prompt)
            if found and s.startswith('╭') and '─' in s:
                break
            if s.startswith('╰') and '─' in s:
                break
            # Stop at empty prompt indicator
            if '│ ›' in s and s.endswith('│'):
                break

            # Skip status/UI patterns
            if any(p in s for p in SKIP_PATTERNS):
                continue
            if any(p in s for p in _STATUS_PATTERNS):
                continue

            # Process response markers
            if s.startswith('~'):
                # Thinking text - include as italics
                c = s[1:].strip()
                if c:
                    lines.append(f"*{c}*")
            elif s.startswith('●'):
                found = True
                c = s[1:].strip()
                if c:
                    lines.append(c)
            elif s.startswith('⎿'):
                c = s[1:].strip()
                if c:
                    lines.append(f"  ↳ {c}")
            elif s and s[0] not in '╭╰' and not (s.startswith('│') and ('›' in s or len(s) < 5)) and not BOX_CHARS_PATTERN.match(s):
                if found:  # Only include lines after we've seen ●
                    lines.append(s)

        if lines and found:
            result = TextCleaner.clean_response('\n'.join(lines))
            # Reject if it's just status messages
            if len(result.replace('\n', ' ').strip()) < 100 and any(p in result for p in _STATUS_PATTERNS):
                return ""
            return result

        return ""

