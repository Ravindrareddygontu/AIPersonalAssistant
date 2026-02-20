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


class TestMessageHistoryFiltering:
    """Test filtering of Auggie's message history UI elements.

    Bug Description:
    - Auggie's terminal UI shows numbered list of previous messages (e.g., "1. user question")
    - During streaming, these lines get redrawn constantly and pollute the output
    - In one case, the user's question appeared 841 times in the answer!
    """

    def test_filters_message_history_lines(self):
        """Test that numbered message history lines are filtered out."""
        question = "i am asking about slack bot"
        processor = StreamProcessor(question)
        state = StreamState()
        state.mark_message_echo_found(0)

        output = """● Let me look at the terminal_agent executor:
1. i am asking about slack bot
backend/services/terminal_agent/executor.py - read file
1. i am asking about slack bot
1. i am asking about slack bot
⎿ Read 213 lines
1. i am asking about slack bot
Now I understand the flow.
1. i am asking about slack bot
The solution is to check status indicators."""

        result = processor.process_chunk(output, state)

        assert result is not None
        assert "i am asking about slack bot" not in result
        assert "terminal_agent executor" in result
        assert "Now I understand the flow" in result

    def test_filters_different_numbered_prefixes(self):
        """Test filtering works for any number prefix (1., 2., 10., etc.)."""
        question = "what are the performance issues"
        processor = StreamProcessor(question)
        state = StreamState()
        state.mark_message_echo_found(0)

        output = """● Here are the issues:
1. what are the performance issues
2. what are the performance issues
10. what are the performance issues
1. Memory leaks in the cache
2. Slow database queries"""

        result = processor.process_chunk(output, state)

        assert result is not None
        assert "what are the performance issues" not in result
        assert "Memory leaks" in result
        assert "Slow database" in result

    def test_keeps_similar_but_different_messages(self):
        """Test that similar messages with different content are kept."""
        question = "list the databases"
        processor = StreamProcessor(question)
        state = StreamState()
        state.mark_message_echo_found(0)

        output = """● Found these:
1. list the databases
1. list the users
2. MongoDB
3. PostgreSQL"""

        result = processor.process_chunk(output, state)

        assert result is not None
        assert "list the databases" not in result
        assert "list the users" in result
        assert "MongoDB" in result

    def test_short_messages_not_filtered(self):
        """Test that short messages (<5 chars) don't trigger filtering."""
        question = "hi"
        processor = StreamProcessor(question)

        assert processor._message_history_pattern is None

    def test_message_history_pattern_built_correctly(self):
        """Test the pattern is built with proper escaping."""
        question = "what is 2+2?"
        processor = StreamProcessor(question)

        assert processor._message_history_pattern is not None
        # Should match exact lines
        assert processor._message_history_pattern.match("1. what is 2+2?")
        assert processor._message_history_pattern.match("99. what is 2+2?")
        assert processor._message_history_pattern.match("1. what is 2+2?  ")  # trailing space ok
        # Should NOT match
        assert not processor._message_history_pattern.match("what is 2+2?")
        assert not processor._message_history_pattern.match("1. different question")
        # Should NOT match when there's content AFTER the question
        assert not processor._message_history_pattern.match("1. what is 2+2? - here's the answer")

    def test_preserves_question_in_legitimate_answer(self):
        """Test that question appearing in AI's answer is NOT filtered."""
        question = "list databases"
        processor = StreamProcessor(question)
        state = StreamState()
        state.mark_message_echo_found(0)

        output = """● Here are the database commands:
1. list databases - shows all DBs
2. create database - makes new DB
3. drop database - deletes a DB"""

        result = processor.process_chunk(output, state)

        assert result is not None
        # The question should appear because it has " - shows all DBs" after it
        assert "list databases" in result
        assert "shows all DBs" in result


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

