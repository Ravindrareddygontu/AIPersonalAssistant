"""
StreamState - Data class for managing stream processing state.

Follows Single Responsibility Principle: Only holds state data.
Uses dataclass for clean, type-safe state management.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StreamState:
    """Holds the state for a streaming response session."""
    
    # Raw output accumulator
    all_output: str = ''
    
    # Timing
    last_data_time: float = field(default_factory=time.time)
    message_sent_time: float = field(default_factory=time.time)
    last_content_change: float = field(default_factory=time.time)
    
    # Processing flags
    saw_message_echo: bool = False
    saw_response_marker: bool = False
    streaming_started: bool = False
    end_pattern_seen: bool = False
    aborted: bool = False
    
    # Content tracking
    last_streamed_content: str = ''
    current_full_content: str = ''  # Full content from process_chunk (may include partial last line)
    streamed_length: int = 0
    output_start_pos: int = 0
    
    # Previous response for de-duplication
    prev_response: str = ''
    
    # Debug flags (to avoid repeated logging)
    _logged_no_match: bool = False
    _logged_no_echo: bool = False
    _logged_wait_times: set = field(default_factory=set)

    # Cache for expensive operations
    _cached_clean: str = ''
    _cached_clean_len: int = 0

    def update_data_time(self) -> None:
        """Update the last data received timestamp."""
        self.last_data_time = time.time()

    def update_content_time(self) -> None:
        """Update the last content change timestamp."""
        self.last_content_change = time.time()

    def mark_message_echo_found(self, position: int) -> None:
        """Mark that we found the message echo at given position."""
        self.saw_message_echo = True
        self.output_start_pos = max(0, position - 50)

    def mark_streaming_started(self) -> None:
        """Mark that streaming has started."""
        self.streaming_started = True

    def mark_response_marker_seen(self) -> None:
        """Mark that we saw a response marker (● or ~)."""
        self.saw_response_marker = True

    def update_streamed_content(self, content: str) -> str:
        """
        Update streamed content and return content to stream.

        For responsiveness, we stream:
        - Complete lines when available (ends with newline)
        - Partial content after a brief delay (for short responses like "4")

        Args:
            content: Full content so far

        Returns:
            Content to stream (complete lines preferred, partial if waiting too long)
        """
        if len(content) <= self.streamed_length:
            return ''

        # Get new content since last stream
        new_content = content[self.streamed_length:]

        # Find the last complete line (ends with newline)
        last_newline = new_content.rfind('\n')

        if last_newline != -1:
            # Have complete lines - send them
            complete_lines = new_content[:last_newline + 1]
            self.streamed_length += len(complete_lines)
            self.last_streamed_content = content[:self.streamed_length]
            self.update_content_time()
            return complete_lines

        # No complete line yet - check if we should send partial content
        # For short responses, send after 0.3s to avoid visible delay
        time_waiting = self.elapsed_since_content
        if time_waiting > 0.3 and len(new_content) > 0:
            # Send partial content - response is likely complete but no newline
            self.streamed_length = len(content)
            self.last_streamed_content = content
            self.update_content_time()
            return new_content

        # Buffer it for now
        return ''

    def flush_remaining_content(self, content: str) -> str:
        """
        Flush any remaining buffered content (for end of stream).

        Args:
            content: Full content

        Returns:
            Any remaining content that wasn't streamed yet
        """
        if len(content) > self.streamed_length:
            remaining = content[self.streamed_length:]
            self.streamed_length = len(content)
            self.last_streamed_content = content
            return remaining.rstrip('\n')  # Clean trailing newlines
        return ''

    @property
    def elapsed_since_data(self) -> float:
        """Time elapsed since last data received."""
        return time.time() - self.last_data_time

    @property
    def elapsed_since_content(self) -> float:
        """Time elapsed since last content change."""
        return time.time() - self.last_content_change

    @property
    def elapsed_since_message(self) -> float:
        """Time elapsed since message was sent."""
        return time.time() - self.message_sent_time

    def should_log_wait(self, seconds: int) -> bool:
        """Check if we should log wait time (avoid duplicate logs)."""
        if seconds in self._logged_wait_times:
            return False
        self._logged_wait_times.add(seconds)
        return True

    def has_substantial_content(self, min_length: int = 50, min_time: float = 5.0) -> bool:
        """Check if we have substantial content (for end detection)."""
        return self.streamed_length > min_length and self.elapsed_since_message > min_time

    # Patterns indicating tools are executing (need extended timeout)
    TOOL_EXECUTING_PATTERNS = [
        'Executing tools',
        'executing tools',
        '- read file',
        '- read directory',
        '- search',
        'Codebase search',
        'Terminal -',
        '↳ Read',
        '↳ Command',
        '↳ Search',
        'Reading file',
        'Searching',
    ]

    def is_tool_executing(self) -> bool:
        """Check if AI is currently executing tools (needs extended timeout)."""
        content = self.last_streamed_content
        if not content:
            return False

        content_end = content[-150:] if len(content) > 150 else content
        for pattern in self.TOOL_EXECUTING_PATTERNS:
            if pattern.lower() in content_end.lower():
                return True
        return False

    def content_looks_complete(self) -> bool:
        """Check if content looks like a complete response.

        IMPORTANT: Uses current_full_content (the actual full content being processed)
        rather than last_streamed_content (which only contains complete lines that have
        been streamed). This prevents false positives where the last complete line ends
        with punctuation but there's more partial content that hasn't been streamed yet.
        """
        # Use current_full_content (most recent full content) if available,
        # otherwise fall back to last_streamed_content
        content = self.current_full_content or self.last_streamed_content
        if not content:
            return False

        # If tools are executing, not complete
        if self.is_tool_executing():
            return False

        # Get last part of content for analysis
        last_chars = content.rstrip()[-30:] if len(content) > 30 else content.rstrip()
        last_word = last_chars.split()[-1] if last_chars.split() else ''

        # Check for common incomplete sentence indicators (articles, prepositions, etc.)
        incomplete_words = {'the', 'a', 'an', 'to', 'of', 'for', 'in', 'on', 'at', 'by', 'with',
                           'and', 'or', 'but', 'if', 'is', 'are', 'was', 'were', 'be', 'been',
                           'this', 'that', 'these', 'those', 'e.g.', 'i.e.', 'etc'}
        if last_word.lower().rstrip('.,?!') in incomplete_words:
            return False

        # Colon at end typically means more content is coming (e.g., "Let me check:")
        # Don't consider this complete
        if last_chars.endswith(':'):
            return False

        # Has proper ending punctuation at the end (not just anywhere)
        has_ending = any(last_chars.endswith(c) for c in ['.', '!', '?', ')', ']', '`', '"', "'"])

        # Require proper ending punctuation - length alone is not enough
        # This prevents cutting off responses that are mid-sentence
        return has_ending

