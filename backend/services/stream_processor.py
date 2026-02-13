"""
StreamProcessor - Handles stream chunk processing and content extraction.

Follows Single Responsibility Principle: Only handles stream processing logic.
"""

import re
import logging
from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.models.stream_state import StreamState

log = logging.getLogger('chat.stream')


class StreamProcessor:
    """Processes streaming output from the Augment terminal."""

    # Patterns for detecting end of response
    END_PATTERN_PROMPT = re.compile(r'│ ›\s*│')
    END_PATTERN_BOX = re.compile(r'╰─+╯')

    def __init__(self, user_message: str):
        self.user_message = user_message
        # Use shorter prefix for matching (terminal may wrap long messages)
        self.message_short = user_message[:20] if len(user_message) > 20 else user_message
        self.message_pattern = re.compile(r'›\s*' + re.escape(self.message_short))

    def process_chunk(self, clean_output: str, state: StreamState) -> str | None:
        """
        Process a chunk of cleaned output and extract response content.

        Args:
            clean_output: ANSI-stripped terminal output
            state: Current stream state

        Returns:
            Extracted content or None if no content found
        """
        # Only search in NEW output (after output_start_pos)
        search_output = clean_output[state.output_start_pos:]

        # Find message echo matches
        matches = list(self.message_pattern.finditer(search_output))
        if not matches:
            if not state._logged_no_match:
                log.debug(f"No match for pattern in search_output. Pattern: {repr(self.message_short[:20])}")
                state._logged_no_match = True
            return None

        # Use the LAST match (most recent echo of our message)
        last_match = self._find_best_match(matches, search_output)
        if not last_match:
            return None

        # Extract content after the message
        after_msg = search_output[last_match.end():]
        return self._extract_response_content(after_msg, state)

    def _find_best_match(self, matches: list, search_output: str):
        """Find the best match from message echo matches."""
        last_match = None
        for match in matches:
            lookahead = search_output[match.end():match.end() + 200]
            nl = lookahead.find('\n')
            first_line = lookahead[:nl] if nl > 0 else lookahead
            rest = lookahead[nl + 1:] if nl > 0 else ""

            if '~' in lookahead or '●' in lookahead:
                last_match = match
            elif '│' not in first_line and '╰' not in first_line:
                if rest.strip() and '│ ›' not in rest[:100]:
                    last_match = match

        return last_match

    def _extract_response_content(self, after_msg: str, state: StreamState) -> str | None:
        """Extract response content from text after message echo."""
        lines = after_msg.split('\n')
        content = []
        in_response = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines before response starts
            if not stripped and not in_response:
                continue

            # Skip box characters
            if BOX_CHARS_PATTERN.match(stripped):
                continue

            # STOP CONDITIONS - marks end of AI response
            if self._is_stop_condition(stripped):
                break

            # Skip patterns we want to filter out
            if any(skip in stripped for skip in SKIP_PATTERNS):
                continue

            # Process response markers
            if stripped.startswith('~') or stripped.startswith('●'):
                in_response = True
                state.mark_response_marker_seen()
                c = stripped[1:].strip()
                if c:
                    content.append(c)
            elif stripped.startswith('⎿') and in_response:
                c = stripped[1:].strip()
                if c:
                    content.append(f"↳ {c}")
            elif in_response and stripped:
                if not any(skip in stripped for skip in ['Claude Opus', 'Version 0.']):
                    content.append(stripped)

        return '\n'.join(content) if content else None

    def _is_stop_condition(self, stripped: str) -> bool:
        """Check if line indicates we should stop extracting."""
        # Prompt indicators
        if stripped.startswith('│ ›') or stripped == '│':
            return True
        # Lone prompt character
        if stripped.startswith('›'):
            return True
        # Previous question being echoed
        if '› ' in stripped and ('?' in stripped or 'files' in stripped.lower() or 'what' in stripped.lower()):
            return True
        # Path-like lines (terminal prompt)
        if stripped.startswith('/') and '/' in stripped[1:] and len(stripped) < 100:
            return True
        # Queued message indicator
        if 'Message will be queued' in stripped:
            return True
        return False

    def check_end_pattern(self, clean_output: str, state: StreamState) -> bool:
        """
        Check if we've reached the end of the response.
        
        Args:
            clean_output: ANSI-stripped terminal output
            state: Current stream state
            
        Returns:
            True if end pattern detected with substantial content
        """
        if not state.streaming_started or not state.saw_response_marker:
            return False

        # Only look in NEW output section
        search_output = clean_output[state.output_start_pos:]
        after_response = (
            search_output[search_output.rfind('●'):] 
            if '●' in search_output 
            else search_output[-500:]
        )

        end_prompt = self.END_PATTERN_PROMPT.search(after_response)
        end_box = self.END_PATTERN_BOX.search(
            after_response[-300:] if len(after_response) > 300 else after_response
        )

        # Require substantial content and complete-looking response
        if (end_prompt or end_box) and state.has_substantial_content() and state.content_looks_complete():
            return True

        return False

