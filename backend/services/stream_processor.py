"""
StreamProcessor - Handles stream chunk processing and content extraction.

Follows Single Responsibility Principle: Only handles stream processing logic.
"""

import re
import logging
from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.models.stream_state import StreamState

log = logging.getLogger('chat.stream')

# Pattern to match auggie status lines ending with "(Xs • esc to interrupt)"
_STATUS_LINE_RE = re.compile(r'\(\d+s\s*[•·]\s*esc to interrupt\)')


class StreamProcessor:
    """Processes streaming output from the Augment terminal."""

    # Patterns for detecting end of response
    END_PATTERN_PROMPT = re.compile(r'│ ›\s*│')
    END_PATTERN_BOX = re.compile(r'╰─+╯')

    # Activity indicators - if present, auggie is still working (don't end yet)
    # These appear in the terminal when auggie is processing/generating
    ACTIVITY_INDICATORS = [
        'Receiving response...',
        'Sending request...',
        'Processing response...',
        'Executing tools...',
        'Summarizing conversation history...',
        '▇▇▇',  # Progress bar
    ]

    def __init__(self, user_message: str):
        self.user_message = user_message
        self._update_pattern(user_message)

    def _update_pattern(self, message: str):
        """Update the message pattern used for echo detection."""
        # Use shorter prefix for matching (terminal may wrap long messages)
        self.message_short = message[:20] if len(message) > 20 else message
        self.message_pattern = re.compile(r'›\s*' + re.escape(self.message_short))

    def update_search_message(self, message: str):
        """Update the message to search for (used for image commands where question differs from original message)."""
        log.info(f"[PROCESSOR] Updating search message to: {message[:30]}...")
        self._update_pattern(message)

    def process_chunk(self, clean_output: str, state: StreamState) -> str | None:
        """
        Process a chunk of cleaned output and extract response content.

        Simple approach: Look for ● markers in NEW output (after output_start_pos).
        No need to find message echo - we already know where we started.

        Args:
            clean_output: ANSI-stripped terminal output
            state: Current stream state

        Returns:
            Extracted content or None if no content found
        """
        # Only search in NEW output (after output_start_pos)
        search_output = clean_output[state.output_start_pos:]

        # Simple: just extract response content from new output
        # The ● marker indicates actual response content
        return self._extract_response_content(search_output, state)

    def _find_best_match(self, matches: list, search_output: str):
        """Find the best match from message echo matches.

        Strategy: Prefer matches that have response markers (● or ~) nearby,
        but fall back to the last match if none have markers nearby.
        This handles cases where the response comes much later than 200 chars.
        """
        best_match = None
        fallback_match = None

        for match in matches:
            lookahead = search_output[match.end():match.end() + 500]  # Increased lookahead
            nl = lookahead.find('\n')
            first_line = lookahead[:nl] if nl > 0 else lookahead

            # Skip matches that look like they're in the middle of UI elements
            if first_line.strip().startswith('│') or first_line.strip().startswith('╰'):
                continue

            # Track this as a potential fallback
            fallback_match = match

            # Prefer matches with response markers nearby
            if '~' in lookahead or '●' in lookahead:
                best_match = match

        # Return best match if found, otherwise fallback to last valid match
        return best_match if best_match else fallback_match

    def _extract_response_content(self, after_msg: str, state: StreamState) -> str | None:
        """Extract response content from text after message echo."""
        lines = after_msg.split('\n')
        content = []
        in_response = False

        # DEBUG: Log lines to understand the output format
        if len(lines) > 5:
            if not hasattr(state, '_debug_extract_logged'):
                log.info(f"[DEBUG_EXTRACT] First 10 lines after message echo:")
                for i, line in enumerate(lines[:10]):
                    log.info(f"[DEBUG_EXTRACT] Line {i}: {repr(line[:100] if len(line) > 100 else line)}")
                state._debug_extract_logged = True
            # Log first occurrence of each marker type (for debugging)
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('●'):
                    if not hasattr(state, '_debug_response_marker_logged'):
                        log.info(f"[DEBUG_MARKER] Found RESPONSE marker (●) at line {i}: {repr(stripped[:80])}")
                        state._debug_response_marker_logged = True
                elif stripped.startswith('~'):
                    if not hasattr(state, '_debug_thinking_marker_logged'):
                        log.info(f"[DEBUG_MARKER] Found THINKING marker (~) at line {i}: {repr(stripped[:80])}")
                        state._debug_thinking_marker_logged = True

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines before response starts
            if not stripped and not in_response:
                continue

            # Skip box characters
            if BOX_CHARS_PATTERN.match(stripped):
                continue

            # IMPORTANT: Check for response markers FIRST, before skip patterns!
            # The ● marker line may contain skip patterns (e.g., "Claude Opus")
            # but we still need to capture it as response content.
            if stripped.startswith('●'):
                in_response = True
                state.mark_response_marker_seen()
                log.info(f"[MARKER] Response marker found: {repr(stripped[:80])}")
                c = stripped[1:].strip()
                if c:
                    content.append(c)
                    log.info(f"[CONTENT] Added from ●: {repr(c[:50])}")
                continue
            elif stripped.startswith('~'):
                # Thinking marker - auggie is working but this is internal reasoning
                # Don't set in_response=True, don't add to content
                continue
            elif stripped.startswith('⎿') and in_response:
                c = stripped[1:].strip()
                if c:
                    content.append(f"↳ {c}")
                continue

            # STOP CONDITIONS - ONLY check if we've already started seeing response
            # Don't stop before finding ● marker!
            if in_response and self._is_stop_condition(stripped, in_response):
                log.info(f"[STOP] Breaking at line {i}: {repr(stripped[:60])}")
                break

            # Skip patterns we want to filter out (only for non-marker lines)
            if any(skip in stripped for skip in SKIP_PATTERNS):
                continue

            # Skip status lines containing "(Xs • esc to interrupt)"
            if _STATUS_LINE_RE.search(stripped):
                continue

            # Regular content lines (after we've seen ● marker)
            if in_response and stripped:
                # Skip UI messages and model identifiers in regular content
                if not any(skip in stripped for skip in ['Claude Opus', 'Version 0.', 'Message will be queued']):
                    content.append(stripped)
                    if len(content) <= 3:
                        log.info(f"[CONTENT] Added line: {repr(stripped[:50])}")

        result = '\n'.join(content) if content else None
        if result:
            log.info(f"[CONTENT] Final content length: {len(result)}, first 100: {repr(result[:100])}")
        return result

    def _is_stop_condition(self, stripped: str, in_response: bool = False) -> bool:
        """Check if line indicates we should stop extracting.

        Args:
            stripped: The stripped line to check
            in_response: Whether we've already started seeing response content
        """
        # "Message will be queued" is a UI notification that appears BEFORE the actual response
        # It has the │ › prefix but should NOT stop extraction
        if 'Message will be queued' in stripped:
            return False

        # Prompt indicators - only stop if we've already seen response content
        # Before seeing response, these could be UI notifications
        if stripped.startswith('│ ›'):
            # Empty prompt is a definitive stop
            rest = stripped[3:].strip()
            if not rest or rest == '│':
                return True
            # If we're already in response, any prompt indicator stops us
            if in_response:
                return True
            # Before response, only stop if it looks like a user input prompt (not UI message)
            return False

        if stripped == '│':
            return True
        # Lone prompt character
        if stripped.startswith('›'):
            return True
        # Previous question being echoed
        if '› ' in stripped and ('?' in stripped or 'files' in stripped.lower() or 'what' in stripped.lower()):
            return True
        # Path-like lines (terminal prompt) - but NOT valid content with paths
        # A terminal prompt is a bare path or path with $ % # > at the end
        if stripped.startswith('/') and '/' in stripped[1:] and len(stripped) < 100:
            # If ends with shell prompt char, it's a terminal prompt
            if stripped.rstrip().endswith(('$', '%', '#', '>')):
                return True
            # If bare path (no spaces/content after), it's likely a terminal prompt
            if len(stripped.split()) == 1:
                return True
        return False

    def _has_activity_indicator(self, text: str) -> bool:
        """Check if terminal output shows auggie is still working."""
        # Look at the end of the text where activity indicators would appear
        check_section = text[-500:] if len(text) > 500 else text
        for indicator in self.ACTIVITY_INDICATORS:
            if indicator in check_section:
                return True
        return False

    def check_end_pattern(self, clean_output: str, state: StreamState) -> bool:
        """
        Check if we've reached the end of the response.

        The definitive signal that auggie finished is when it shows an EMPTY input prompt:
        │ ›                                                                          │
        ╰────────────────────────────────────────────────────────────────────────────╯

        This means auggie is waiting for the next input, i.e., response is complete.

        IMPORTANT: We also check:
        1. If activity indicators are present (Sending request..., etc.) - NOT complete
        2. If the content looks complete (has proper ending punctuation)

        This prevents cutting off responses that are still being generated.

        Args:
            clean_output: ANSI-stripped terminal output
            state: Current stream state

        Returns:
            True if end pattern detected (empty prompt ready for input)
        """
        if not state.streaming_started or not state.saw_response_marker:
            return False

        # Only look in NEW output section, focus on the end
        search_output = clean_output[state.output_start_pos:]

        # Look at the last portion where end pattern would appear
        last_section = search_output[-800:] if len(search_output) > 800 else search_output

        # FIRST CHECK: If activity indicators present, auggie is still working - don't end
        if self._has_activity_indicator(last_section):
            log.debug("[END_DETECT] Activity indicator found - auggie still working")
            return False

        # The DEFINITIVE end signal: empty input prompt box
        # Pattern: │ ›  followed by mostly spaces and ending with │
        # This indicates auggie is ready for next input = response complete
        empty_prompt_pattern = re.compile(r'│ ›\s{20,}│')

        if empty_prompt_pattern.search(last_section):
            # Found empty prompt pattern - this is the definitive signal
            # Trust this signal when we have substantial content
            if state.has_substantial_content(min_length=10, min_time=1.0):
                log.info("[END_DETECT] Found empty input prompt - response complete")
                return True

        # Secondary check: Look for the COMPLETE end sequence:
        # 1. Empty prompt line: │ ›  (spaces) │
        # 2. Followed by box bottom: ╰───...───╯
        if state.has_substantial_content(min_length=10, min_time=1.0):
            end_section = last_section[-400:] if len(last_section) > 400 else last_section

            prompt_match = self.END_PATTERN_PROMPT.search(end_section)
            box_match = self.END_PATTERN_BOX.search(end_section)

            if prompt_match and box_match:
                if box_match.start() >= prompt_match.start() - 50:
                    log.info("[END_DETECT] Found prompt + box bottom sequence")
                    return True

        return False

