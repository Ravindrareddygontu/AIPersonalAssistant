import time
from dataclasses import dataclass, field


@dataclass
class StreamState:
    # Raw output accumulator
    all_output: str = ''
    clean_output: str = ''
    
    # Timing
    last_data_time: float = field(default_factory=time.time)
    message_sent_time: float = field(default_factory=time.time)
    last_content_change: float = field(default_factory=time.time)
    last_activity_time: float = field(default_factory=time.time)

    # Activity tracking (for extended timeouts during processing)
    current_activity: str = ''
    
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

    # Incremental ANSI stripping helpers
    _raw_tail: str = ''
    _clean_tail: str = ''

    def update_data_time(self) -> None:
        self.last_data_time = time.time()

    def update_content_time(self) -> None:
        self.last_content_change = time.time()

    def update_activity(self, activity: str) -> None:
        self.current_activity = activity
        self.last_activity_time = time.time()

    def has_recent_activity(self, timeout: float = 120.0) -> bool:
        if not self.current_activity:
            return False
        return (time.time() - self.last_activity_time) < timeout

    @property
    def elapsed_since_activity(self) -> float:
        return time.time() - self.last_activity_time

    def mark_message_echo_found(self, position: int) -> None:
        self.saw_message_echo = True
        self.output_start_pos = max(0, position - 50)

    def mark_streaming_started(self) -> None:
        self.streaming_started = True

    def mark_response_marker_seen(self) -> None:
        self.saw_response_marker = True

    def update_streamed_content(self, content: str) -> str:
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
        if len(content) > self.streamed_length:
            remaining = content[self.streamed_length:]
            self.streamed_length = len(content)
            self.last_streamed_content = content
            return remaining.rstrip('\n')  # Clean trailing newlines
        return ''

    @property
    def elapsed_since_data(self) -> float:
        return time.time() - self.last_data_time

    @property
    def elapsed_since_content(self) -> float:
        return time.time() - self.last_content_change

    @property
    def elapsed_since_message(self) -> float:
        return time.time() - self.message_sent_time

    def should_log_wait(self, seconds: int) -> bool:
        if seconds in self._logged_wait_times:
            return False
        self._logged_wait_times.add(seconds)
        return True

    def has_substantial_content(self, min_length: int = 50, min_time: float = 5.0) -> bool:
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
        content = self.last_streamed_content
        if not content:
            return False

        content_end = content[-150:] if len(content) > 150 else content
        for pattern in self.TOOL_EXECUTING_PATTERNS:
            if pattern.lower() in content_end.lower():
                return True
        return False

    def content_looks_complete(self) -> bool:
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
