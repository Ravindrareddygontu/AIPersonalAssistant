"""
Tests for StreamProcessor - specifically testing the bug where
identical question prefixes with different contexts returned wrong answers.

Bug Description:
- Question 3: "list them" (context: databases) → Answer about databases ✓
- Question 5: "list them" (context: performance issues) → Answer about databases ✗
  Should have been about performance issues!

Root Cause: Caching of regex match positions across different questions
with the same prefix caused the wrong content to be extracted.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.stream_processor import StreamProcessor
from backend.models.stream_state import StreamState


class TestStreamProcessorSamePrefix:
    """Test that questions with same prefix but different context get correct answers."""

    def create_terminal_output(self, question: str, response: str) -> str:
        """Create simulated terminal output with question echo and response."""
        return f"""
╭─────────────────────────────────────────────────────────────────────────────╮
│ › {question}                                                                │
╰─────────────────────────────────────────────────────────────────────────────╯

● {response}

╭─────────────────────────────────────────────────────────────────────────────╮
│ ›                                                                           │
╰─────────────────────────────────────────────────────────────────────────────╯
"""

    def test_same_prefix_different_context_first_question(self):
        """Test first 'list them' question about databases."""
        question = "list them"
        response = "Based on my search, there is only one database: MongoDB"
        
        processor = StreamProcessor(question)
        state = StreamState()
        
        terminal_output = self.create_terminal_output(question, response)
        
        result = processor.process_chunk(terminal_output, state)
        
        assert result is not None
        assert "MongoDB" in result
        assert "database" in result.lower()

    def test_same_prefix_different_context_second_question(self):
        """Test second 'list them' question about performance issues."""
        question = "list them"
        response = "Here are the performance issues: 1. Small buffer size 2. No caching"
        
        processor = StreamProcessor(question)
        state = StreamState()
        
        terminal_output = self.create_terminal_output(question, response)
        
        result = processor.process_chunk(terminal_output, state)
        
        assert result is not None
        assert "performance" in result.lower()
        assert "buffer" in result.lower()

    def test_sequential_same_prefix_questions_isolated(self):
        """
        Test that two sequential questions with same prefix are isolated.
        This is the main regression test for the caching bug.
        """
        question = "list them"
        
        # First question context: databases
        response1 = "Based on my search, there is only one database: MongoDB"
        processor1 = StreamProcessor(question)
        state1 = StreamState()
        terminal_output1 = self.create_terminal_output(question, response1)
        result1 = processor1.process_chunk(terminal_output1, state1)
        
        # Second question context: performance issues (NEW processor and state)
        response2 = "Here are the performance issues: 1. Small buffer 2. No caching"
        processor2 = StreamProcessor(question)
        state2 = StreamState()
        terminal_output2 = self.create_terminal_output(question, response2)
        result2 = processor2.process_chunk(terminal_output2, state2)
        
        # Results should be different - each should match its own response
        assert result1 is not None
        assert result2 is not None
        assert "MongoDB" in result1
        assert "performance" in result2.lower()
        # Critical: result2 should NOT contain database content
        assert "MongoDB" not in result2

    def test_state_isolation_between_requests(self):
        """Test that StreamState is properly isolated between requests."""
        state1 = StreamState()
        state2 = StreamState()
        
        # Modify state1
        state1.saw_message_echo = True
        state1.output_start_pos = 100
        state1.streamed_length = 500
        
        # state2 should be unaffected
        assert state2.saw_message_echo == False
        assert state2.output_start_pos == 0
        assert state2.streamed_length == 0


class TestStreamProcessorBasic:
    """Basic functionality tests for StreamProcessor."""

    def test_processor_initialization(self):
        """Test processor initializes with correct message pattern."""
        processor = StreamProcessor("test message")
        assert processor.user_message == "test message"
        assert processor.message_short == "test message"

    def test_processor_long_message_truncation(self):
        """Test that long messages are truncated for pattern matching."""
        long_message = "a" * 50
        processor = StreamProcessor(long_message)
        assert len(processor.message_short) == 20

    def test_no_match_returns_none(self):
        """Test that no match in output returns None."""
        processor = StreamProcessor("find this")
        state = StreamState()
        
        # Output without the question echo
        output = "Some random terminal output without the question"
        
        result = processor.process_chunk(output, state)
        assert result is None

    def test_empty_response_returns_none(self):
        """Test that empty response after question returns None."""
        processor = StreamProcessor("test")
        state = StreamState()
        
        # Output with question but no response
        output = "│ › test\n│ ›"
        
        result = processor.process_chunk(output, state)
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

