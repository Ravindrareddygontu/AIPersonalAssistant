"""
Tests for stream_state.py - StreamState dataclass and its methods.

Tests cover:
- StreamState initialization and defaults
- update_data_time, update_content_time: Time tracking
- mark_message_echo_found: Echo detection
- update_streamed_content: Content streaming updates
- flush_remaining_content: Final content flush
- has_substantial_content: Content validation
- is_tool_executing: Tool execution detection
- content_looks_complete: Completion detection
"""

import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.stream_state import StreamState


class TestStreamStateInitialization:
    """Test StreamState initialization and defaults."""

    def test_default_values(self):
        """Test default initialization values."""
        state = StreamState()

        assert state.all_output == ""
        assert state.prev_response == ""
        assert state.saw_message_echo == False
        assert state.saw_response_marker == False
        assert state.last_streamed_content == ""
        assert state.streamed_length == 0
        assert state.output_start_pos == 0

    def test_custom_prev_response(self):
        """Test initialization with custom prev_response."""
        state = StreamState(prev_response="Previous response")
        assert state.prev_response == "Previous response"


class TestTimeTracking:
    """Test time tracking methods."""

    def test_update_data_time(self):
        """Test update_data_time updates timestamp."""
        state = StreamState()
        initial_time = state.last_data_time
        time.sleep(0.01)  # Small delay
        state.update_data_time()
        assert state.last_data_time >= initial_time

    def test_update_content_time(self):
        """Test update_content_time updates timestamp."""
        state = StreamState()
        initial_time = state.last_content_change
        time.sleep(0.01)
        state.update_content_time()
        assert state.last_content_change >= initial_time


class TestMessageEchoDetection:
    """Test message echo detection."""

    def test_mark_message_echo_found(self):
        """Test marking message echo as found."""
        state = StreamState()
        assert state.saw_message_echo == False
        assert state.output_start_pos == 0

        state.mark_message_echo_found(100)

        assert state.saw_message_echo == True
        # output_start_pos is set to max(0, position - 50)
        assert state.output_start_pos == 50

    def test_mark_message_echo_at_start(self):
        """Test marking echo at start position."""
        state = StreamState()
        state.mark_message_echo_found(10)

        # max(0, 10 - 50) = 0
        assert state.output_start_pos == 0


class TestUpdateStreamedContent:
    """Test streamed content updates."""

    def test_update_streamed_content_with_newline(self):
        """Test content update with complete lines."""
        state = StreamState()
        result = state.update_streamed_content("Hello, world!\n")

        assert result == "Hello, world!\n"
        assert state.streamed_length == 14

    def test_update_streamed_content_incremental(self):
        """Test incremental content updates."""
        state = StreamState()
        state.update_streamed_content("Line 1\n")
        result = state.update_streamed_content("Line 1\nLine 2\n")

        assert result == "Line 2\n"

    def test_update_no_new_content(self):
        """Test when no new content is available."""
        state = StreamState()
        state.update_streamed_content("Hello\n")
        result = state.update_streamed_content("Hello\n")

        assert result == ""


class TestFlushRemainingContent:
    """Test final content flush."""

    def test_flush_remaining_content(self):
        """Test flushing remaining content."""
        state = StreamState()
        state.streamed_length = 5

        remaining = state.flush_remaining_content("Current content here")

        # Should return content that wasn't sent yet
        assert isinstance(remaining, str)
        assert "content" in remaining.lower()

    def test_flush_when_all_sent(self):
        """Test flush when all content was already sent."""
        state = StreamState()
        content = "Content"
        state.streamed_length = len(content)

        remaining = state.flush_remaining_content(content)
        assert remaining == ""


class TestHasSubstantialContent:
    """Test substantial content detection."""

    def test_empty_content(self):
        """Test empty content is not substantial."""
        state = StreamState()
        assert state.has_substantial_content() == False

    def test_short_content_not_substantial(self):
        """Test short content is not substantial."""
        state = StreamState()
        state.streamed_length = 10
        assert state.has_substantial_content() == False

    def test_substantial_content_needs_length_and_time(self):
        """Test that substantial content needs both length and time."""
        state = StreamState()
        # Has enough length but not enough time
        state.streamed_length = 100
        # message_sent_time is set to now, so elapsed is ~0
        assert state.has_substantial_content() == False


class TestIsToolExecuting:
    """Test tool execution detection."""

    def test_no_tool_executing(self):
        """Test when no tool is executing."""
        state = StreamState()
        state.last_streamed_content = "Normal conversation output"
        assert state.is_tool_executing() == False

    def test_terminal_executing(self):
        """Test Terminal tool detection."""
        state = StreamState()
        state.last_streamed_content = "Response\nTerminal - Running command"
        assert state.is_tool_executing() == True

    def test_codebase_search_executing(self):
        """Test Codebase Search tool detection."""
        state = StreamState()
        state.last_streamed_content = "Checking\nCodebase search results"
        assert state.is_tool_executing() == True

    def test_empty_content_no_tool(self):
        """Test empty content returns False."""
        state = StreamState()
        state.last_streamed_content = ""
        assert state.is_tool_executing() == False


class TestContentLooksComplete:
    """Test content completion detection."""

    def test_empty_not_complete(self):
        """Test empty content is not complete."""
        state = StreamState()
        assert state.content_looks_complete() == False

    def test_ends_with_period(self):
        """Test content ending with period looks complete."""
        state = StreamState()
        state.last_streamed_content = "This is a complete sentence."
        assert state.content_looks_complete() == True

    def test_ends_with_question_mark(self):
        """Test content ending with question mark."""
        state = StreamState()
        state.last_streamed_content = "Is this complete?"
        assert state.content_looks_complete() == True

    def test_ends_mid_sentence(self):
        """Test content ending mid-sentence."""
        state = StreamState()
        state.last_streamed_content = "This sentence is not finished and"
        assert state.content_looks_complete() == False

    def test_ends_with_colon(self):
        """Test content ending with colon is not complete."""
        state = StreamState()
        state.last_streamed_content = "Here is the code:"
        assert state.content_looks_complete() == False

    def test_ends_with_code_block(self):
        """Test content ending with code block."""
        state = StreamState()
        state.last_streamed_content = "Here's the code:\n```python\nprint('hello')\n```"
        assert state.content_looks_complete() == True


class TestStreamStateIntegration:
    """Integration tests for StreamState workflow."""

    def test_full_streaming_workflow(self):
        """Test complete streaming workflow."""
        state = StreamState(prev_response="")

        # Step 1: Receive initial output
        state.all_output = "User question echoed\n● Response starts"
        state.update_data_time()

        # Step 2: Mark message echo
        state.mark_message_echo_found(0)
        assert state.saw_message_echo == True

        # Step 3: Update content with newline
        result = state.update_streamed_content("Response starts\n")
        assert result == "Response starts\n"

        # Step 4: More content
        result = state.update_streamed_content("Response starts\nMore text here.\n")
        assert "More text" in result

    def test_elapsed_time_properties(self):
        """Test elapsed time property calculations."""
        state = StreamState()
        time.sleep(0.01)

        assert state.elapsed_since_data >= 0.01
        assert state.elapsed_since_content >= 0.01
        assert state.elapsed_since_message >= 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

