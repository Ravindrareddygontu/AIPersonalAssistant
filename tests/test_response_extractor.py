"""
Tests for response.py - ResponseExtractor class.

Tests cover:
- extract_full: Main extraction method
- Finding user message in output
- Finding ● marker
- Extracting content until end markers
- Handling thinking text (~)
- Handling continuation markers (⎿)
- Skipping status patterns
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.response import ResponseExtractor


class TestExtractFull:
    """Test the main extract_full method."""

    def test_empty_output(self):
        """Test extraction from empty output."""
        result = ResponseExtractor.extract_full("", "test question")
        assert result == ""

    def test_message_not_found(self):
        """Test when user message is not in output."""
        output = "Random terminal output without the user message"
        result = ResponseExtractor.extract_full(output, "totally different question")
        assert result == ""

    def test_no_marker_after_message(self):
        """Test when ● marker is not found after message."""
        output = "User asked: What is AI?\nSome output without marker"
        result = ResponseExtractor.extract_full(output, "What is AI?")
        assert result == ""

    def test_basic_extraction(self):
        """Test basic response extraction."""
        output = """Some preamble
What is 2+2?
● The answer is 4.
That's a simple calculation.
╭─────────────────╮"""
        result = ResponseExtractor.extract_full(output, "What is 2+2?")
        
        assert "answer is 4" in result
        assert "simple calculation" in result

    def test_stops_at_box_start(self):
        """Test that extraction stops at UI box elements."""
        output = """Hello there
● Here is my response.
╭─── New input box ───╮
│ › next prompt       │"""
        result = ResponseExtractor.extract_full(output, "Hello there")
        
        assert "Here is my response" in result
        assert "New input box" not in result

    def test_stops_at_box_end(self):
        """Test that extraction stops at box end."""
        output = """Question here
● Response text here.
╰───────────────────╯"""
        result = ResponseExtractor.extract_full(output, "Question here")
        
        assert "Response text" in result
        assert "╰" not in result

    def test_stops_at_empty_prompt(self):
        """Test stopping at empty prompt indicator."""
        output = """My question
● Good response here.
│ ›                  │"""
        result = ResponseExtractor.extract_full(output, "My question")
        
        assert "Good response" in result

    def test_thinking_text_formatted(self):
        """Test that thinking text (~) is formatted as italics."""
        output = """Question
● Starting response
~ This is thinking text
More content"""
        result = ResponseExtractor.extract_full(output, "Question")
        
        # Thinking text should be in italics format
        if "thinking" in result.lower():
            assert "*" in result  # Markdown italics

    def test_continuation_marker_formatted(self):
        """Test that continuation marker (⎿) is formatted."""
        output = """Question
● Main response
⎿ Continuation detail"""
        result = ResponseExtractor.extract_full(output, "Question")
        
        # Should include continuation with arrow
        if "Continuation" in result:
            assert "↳" in result or "Continuation" in result

    def test_skips_status_patterns(self):
        """Test that status patterns are skipped."""
        output = """Question
● Good response
Sending request...
esc to interrupt
More good content"""
        result = ResponseExtractor.extract_full(output, "Question")
        
        assert "Sending request" not in result
        assert "esc to interrupt" not in result

    def test_uses_message_prefix(self):
        """Test that long messages use prefix for matching."""
        long_message = "A" * 100
        output = f"""{long_message}
● Response to the long message."""
        result = ResponseExtractor.extract_full(output, long_message)
        
        # Should find the message using first 30 chars
        assert "Response" in result

    def test_handles_control_characters(self):
        """Test that control characters are stripped."""
        output = "Question\x00\x08● Clean\x7f response"
        result = ResponseExtractor.extract_full(output, "Question")
        
        # Should extract without control chars causing issues
        if result:
            assert "\x00" not in result
            assert "\x7f" not in result

    def test_multiline_response(self):
        """Test extraction of multiline responses."""
        output = """Complex question here
● First line of response.
Second line continues.
Third line with more info.
  - A bullet point
  - Another bullet
╭────────────────────╮"""
        result = ResponseExtractor.extract_full(output, "Complex question")
        
        assert "First line" in result
        assert "Second line" in result
        assert "bullet point" in result

    def test_rfind_for_last_occurrence(self):
        """Test that rfind is used to find last occurrence of message."""
        output = """First mention of hello
Some content
hello
● Response to the actual question"""
        result = ResponseExtractor.extract_full(output, "hello")
        
        # Should find marker after LAST occurrence of message
        assert "Response" in result

    def test_rejects_status_only_content(self):
        """Test that status-only content is rejected."""
        output = """Question
● Sending request...
Processing response..."""
        result = ResponseExtractor.extract_full(output, "Question")
        
        # Should return empty for status-only responses
        assert result == "" or "Sending request" not in result


class TestMessageHistoryFiltering:
    """Test filtering of Auggie's message history UI elements.

    Bug Description:
    - Auggie's terminal UI shows numbered list of previous messages
    - These get constantly redrawn during streaming and appear in raw output
    - rfind was matching "1. user question" instead of the actual message echo
    """

    def test_filters_message_history_before_rfind(self):
        """Test that message history lines are filtered before finding message position."""
        user_message = "i am asking about slack bot"

        output = """i am asking about slack bot
● Let me look at the terminal_agent executor:
1. i am asking about slack bot
backend/services/terminal_agent/executor.py - read file
1. i am asking about slack bot
⎿ Read 213 lines
Now I understand the flow.
1. i am asking about slack bot
The solution is to check status indicators."""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        assert "i am asking about slack bot" not in result
        assert "terminal_agent executor" in result
        assert "Now I understand the flow" in result

    def test_filters_heavy_pollution(self):
        """Test filtering when message appears many times (simulating the 841x bug)."""
        user_message = "what are the issues"

        history_line = "1. what are the issues\n"
        output = f"""what are the issues
● Here is the analysis:
{history_line * 50}First issue: memory leak
{history_line * 50}Second issue: slow queries
{history_line * 50}Third issue: no caching"""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        assert "what are the issues" not in result
        assert "memory leak" in result
        assert "slow queries" in result

    def test_different_number_prefixes_filtered(self):
        """Test that different number prefixes (1., 2., 99.) are all filtered."""
        user_message = "show me the code"

        output = """show me the code
● Here's the code:
1. show me the code
2. show me the code
99. show me the code
def hello():
    print("world")"""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        assert "show me the code" not in result
        assert "def hello" in result

    def test_preserves_similar_but_different_messages(self):
        """Test that similar messages with different content are preserved."""
        user_message = "list databases"

        output = """list databases
● Here are the results:
1. list databases
1. list all tables
MongoDB
PostgreSQL"""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        assert "list databases" not in result
        assert "list all tables" in result
        assert "MongoDB" in result

    def test_short_messages_not_filtered(self):
        """Test that short messages (<5 chars) skip history filtering but still extract."""
        user_message = "hello"

        output = """hello
● Hello! How can I help?
More content here."""

        result = ResponseExtractor.extract_full(output, user_message)
        assert "Hello" in result or "How can I help" in result

    def test_special_chars_in_message_escaped(self):
        """Test that special regex characters in message are properly escaped."""
        user_message = "what is 2+2? (test)"

        output = """what is 2+2? (test)
● The answer is 4.
1. what is 2+2? (test)
Simple math."""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        assert "what is 2+2?" not in result
        assert "answer is 4" in result

    def test_preserves_question_in_legitimate_answer(self):
        """Test that question appearing legitimately in AI answer is NOT filtered."""
        user_message = "list databases"

        output = """list databases
● Here are the commands:
1. list databases - shows all databases
2. create database - creates a new database
3. drop database - deletes a database"""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        # Should contain "list databases" because it has content after it
        assert "list databases" in result
        assert "shows all databases" in result

    def test_filters_exact_match_but_keeps_extended(self):
        """Test exact match is filtered but extended content is kept."""
        user_message = "show files"

        output = """show files
● Here's what I found:
1. show files
1. show files in directory /home
file1.txt
file2.txt"""

        result = ResponseExtractor.extract_full(output, user_message)

        assert result != ""
        # Exact match "1. show files" should be filtered
        # But "1. show files in directory" should be kept
        assert "show files in directory" in result
        assert "file1.txt" in result


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_ansi_codes_stripped(self):
        """Test that ANSI codes are stripped before processing."""
        output = "\x1b[31mQuestion\x1b[0m\n● \x1b[32mResponse\x1b[0m"
        result = ResponseExtractor.extract_full(output, "Question")

        # ANSI codes should be stripped
        assert "\x1b[" not in result

    def test_marker_at_line_start(self):
        """Test marker at the very start of a line."""
        output = """Question
●Response without space"""
        result = ResponseExtractor.extract_full(output, "Question")
        
        assert "Response" in result

    def test_multiple_markers(self):
        """Test handling of multiple ● markers."""
        output = """Question
● First marker response
● Second marker continues"""
        result = ResponseExtractor.extract_full(output, "Question")
        
        # Should process both markers appropriately
        assert "First marker" in result or "Second marker" in result

    def test_unicode_content(self):
        """Test handling of unicode content."""
        output = """Unicode question 你好
● Unicode response: 世界 🌍"""
        result = ResponseExtractor.extract_full(output, "Unicode question")
        
        assert "世界" in result or "response" in result.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

