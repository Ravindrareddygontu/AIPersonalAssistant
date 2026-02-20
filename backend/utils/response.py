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

    _NOT_SET = object()

    @staticmethod
    def extract_full(
        raw_output: str,
        user_message: str,
        response_marker: str = _NOT_SET,
        thinking_marker: str = _NOT_SET,
        continuation_marker: str = _NOT_SET,
    ) -> str:
        if response_marker is ResponseExtractor._NOT_SET:
            response_marker = ResponseExtractor.DEFAULT_RESPONSE_MARKER
        if thinking_marker is ResponseExtractor._NOT_SET:
            thinking_marker = ResponseExtractor.DEFAULT_THINKING_MARKER
        if continuation_marker is ResponseExtractor._NOT_SET:
            continuation_marker = ResponseExtractor.DEFAULT_CONTINUATION_MARKER

        text = _CTRL_CHARS_RE.sub('', TextCleaner.strip_ansi(raw_output))
        full_message = user_message.strip()

        # Build pattern to filter exact Auggie message history lines (e.g., "1. user's question")
        # Only filters exact matches to preserve legitimate content like "1. list databases - shows all DBs"
        msg_history_pattern = None
        if len(full_message) >= 5:
            msg_history_pattern = re.compile(r'^\d+\.\s+' + re.escape(full_message) + r'\s*$', re.IGNORECASE)

        # Simple approach: Find the first response marker (●) and extract from there
        # Everything before ● is echo/UI noise, everything after is the response
        marker_pos = text.find(response_marker)
        if marker_pos < 0:
            log.debug(f"[EXTRACT] No {response_marker} marker found in output")
            return ""

        content_start = text[marker_pos:]
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

            # Skip Auggie message history lines (e.g., "1. user's question")
            if msg_history_pattern and msg_history_pattern.match(s):
                continue

            if thinking_marker and s.startswith(thinking_marker):
                c = s[len(thinking_marker):].strip()
                if c:
                    lines.append(f"*{c}*")
            elif response_marker and s.startswith(response_marker):
                found = True
                c = s[len(response_marker):].strip()
                if c:
                    lines.append(c)
            elif continuation_marker and s.startswith(continuation_marker):
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

