"""
Tests for content_cleaner.py - ContentCleaner class for cleaning terminal artifacts.

Tests cover:
- clean_assistant_content: Main cleaning method
- _is_prompt_line: Detecting prompt indicators
- _is_path_line: Detecting terminal path prompts
- _is_empty_box_line: Detecting empty box formatting
- _is_box_only_line: Detecting box-only lines
- _is_garbage_line: Detecting escape code garbage
- _clean_trailing_garbage: Removing trailing garbage
- strip_previous_response: Removing previous response from content
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.content_cleaner import ContentCleaner


class TestCleanAssistantContent:
    """Test the main content cleaning method."""

    def test_clean_empty_content(self):
        """Test cleaning empty content."""
        assert ContentCleaner.clean_assistant_content("") == ""
        assert ContentCleaner.clean_assistant_content(None) is None

    def test_clean_simple_text(self):
        """Test cleaning simple text with no artifacts."""
        content = "This is a simple response."
        result = ContentCleaner.clean_assistant_content(content)
        assert result == "This is a simple response."

    def test_removes_prompt_line(self):
        """Test that content after prompt line is removed."""
        content = "Good response here.\n› more input"
        result = ContentCleaner.clean_assistant_content(content)
        assert result == "Good response here."

    def test_removes_path_prompt(self):
        """Test that bare path prompts are removed."""
        content = "Response text.\n/home/user/project"
        result = ContentCleaner.clean_assistant_content(content)
        assert result == "Response text."

    def test_keeps_path_with_content(self):
        """Test that paths with content are kept."""
        content = "The config is at /etc/nginx/nginx.conf with settings."
        result = ContentCleaner.clean_assistant_content(content)
        assert "/etc/nginx/nginx.conf" in result

    def test_removes_empty_box_lines(self):
        """Test that empty box lines are removed."""
        content = "Text\n│                                                                          │\nMore text"
        result = ContentCleaner.clean_assistant_content(content)
        assert "│                                                                          │" not in result

    def test_removes_box_only_lines(self):
        """Test that lines with only box characters are removed."""
        content = "Text\n───────\nMore text"
        result = ContentCleaner.clean_assistant_content(content)
        assert "───────" not in result

    def test_removes_trailing_garbage(self):
        """Test that trailing escape code remnants are removed."""
        content = "Text;38"
        result = ContentCleaner.clean_assistant_content(content)
        assert result == "Text"

    def test_multiline_content(self):
        """Test cleaning multiline content."""
        content = """Here is my response.
It has multiple lines.
With good content."""
        result = ContentCleaner.clean_assistant_content(content)
        assert "Here is my response." in result
        assert "multiple lines" in result


class TestIsPromptLine:
    """Test prompt line detection."""

    def test_prompt_with_arrow(self):
        """Test detecting › prompt."""
        assert ContentCleaner._is_prompt_line("› ") == True
        assert ContentCleaner._is_prompt_line("›") == True

    def test_box_prompt(self):
        """Test detecting box with prompt."""
        assert ContentCleaner._is_prompt_line("│ ›") == True
        assert ContentCleaner._is_prompt_line("│") == True

    def test_normal_text(self):
        """Test that normal text is not detected as prompt."""
        assert ContentCleaner._is_prompt_line("Normal text") == False
        assert ContentCleaner._is_prompt_line("Code here") == False


class TestIsPathLine:
    """Test path line detection."""

    def test_bare_unix_path(self):
        """Test bare Unix path detection."""
        assert ContentCleaner._is_path_line("/home/user/project") == True
        assert ContentCleaner._is_path_line("/var/www") == True

    def test_path_with_shell_prompt(self):
        """Test path with shell prompt."""
        assert ContentCleaner._is_path_line("/home/user$") == True
        assert ContentCleaner._is_path_line("/home/user %") == True
        assert ContentCleaner._is_path_line("/home/user#") == True

    def test_path_with_content(self):
        """Test path with content (should not be detected as path line)."""
        assert ContentCleaner._is_path_line("/etc/nginx is the config dir") == False
        assert ContentCleaner._is_path_line("/usr/bin/python3 script.py") == False

    def test_not_a_path(self):
        """Test non-path strings."""
        assert ContentCleaner._is_path_line("normal text") == False
        assert ContentCleaner._is_path_line("100/200 files") == False

    def test_very_long_path(self):
        """Test that very long paths are not detected (likely content)."""
        long_path = "/a" + "/b" * 60  # 121 chars
        assert ContentCleaner._is_path_line(long_path) == False


class TestIsEmptyBoxLine:
    """Test empty box line detection."""

    def test_empty_box_line(self):
        """Test detection of empty box line."""
        line = "│                                                                          │"
        assert ContentCleaner._is_empty_box_line(line) == True

    def test_non_empty_box_line(self):
        """Test that non-empty box line is not detected."""
        assert ContentCleaner._is_empty_box_line("│ Text │") == False
        assert ContentCleaner._is_empty_box_line("Normal text") == False


class TestIsBoxOnlyLine:
    """Test box-only line detection."""

    def test_box_characters(self):
        """Test lines with only box characters."""
        assert ContentCleaner._is_box_only_line("───────") == True
        assert ContentCleaner._is_box_only_line("│││") == True
        assert ContentCleaner._is_box_only_line("╭─────╮") == True

    def test_mixed_content(self):
        """Test lines with text and box characters."""
        assert ContentCleaner._is_box_only_line("│ Text │") == False

    def test_empty_string(self):
        """Test empty string returns falsy value."""
        # Empty string returns '' which is falsy (not False)
        assert not ContentCleaner._is_box_only_line("")


class TestIsGarbageLine:
    """Test garbage line detection."""

    def test_numeric_garbage(self):
        """Test numeric escape code remnants."""
        assert ContentCleaner._is_garbage_line(";123") == True
        assert ContentCleaner._is_garbage_line("45") == True

    def test_terminal_ui_garbage(self):
        """Test terminal UI artifact detection (SA, cursor codes, etc)."""
        assert ContentCleaner._is_garbage_line("SA") == True
        assert ContentCleaner._is_garbage_line("A") == True
        assert ContentCleaner._is_garbage_line("H") == True
        assert ContentCleaner._is_garbage_line("K") == True
        assert ContentCleaner._is_garbage_line("m") == True
        assert ContentCleaner._is_garbage_line("1;5") == True
        assert ContentCleaner._is_garbage_line("?25h") == True
        assert ContentCleaner._is_garbage_line("?25l") == True

    def test_partial_escape_cleaning(self):
        """Test cleaning partial escape sequences from mid-line."""
        assert ContentCleaner._clean_partial_escapes("Sen[2K") == "Sen"
        assert ContentCleaner._clean_partial_escapes("text[1A more") == "text more"
        assert ContentCleaner._clean_partial_escapes("foo[0m bar") == "foo bar"
        assert ContentCleaner._clean_partial_escapes("[?25h visible") == " visible"
        assert ContentCleaner._clean_partial_escapes("normal text") == "normal text"
        assert ContentCleaner._clean_partial_escapes("color[38;2;255;0;0m red") == "color red"

    def test_normal_text(self):
        """Test normal text is not garbage."""
        assert ContentCleaner._is_garbage_line("Hello") == False
        assert ContentCleaner._is_garbage_line("Code 42") == False
        assert ContentCleaner._is_garbage_line("Save the file") == False
        assert ContentCleaner._is_garbage_line("USA") == False

    def test_empty_string(self):
        """Test empty string is not garbage."""
        assert ContentCleaner._is_garbage_line("") == False


class TestCleanTrailingGarbage:
    """Test trailing garbage removal."""

    def test_semicolon_ending(self):
        """Test removing trailing semicolon garbage."""
        result = ContentCleaner._clean_trailing_garbage("Text;", "Text;")
        assert result == "Text"

    def test_normal_line(self):
        """Test that normal lines are unchanged."""
        result = ContentCleaner._clean_trailing_garbage("Normal text", "Normal text")
        assert result == "Normal text"


class TestStripPreviousResponse:
    """Test previous response stripping."""

    def test_strip_previous(self):
        """Test stripping previous response from content."""
        previous = "Old response"
        content = "Old responseNew response"
        result = ContentCleaner.strip_previous_response(content, previous)
        assert result == "New response"

    def test_no_overlap(self):
        """Test when there's no overlap."""
        result = ContentCleaner.strip_previous_response("New content", "Different")
        assert result == "New content"

    def test_empty_inputs(self):
        """Test with empty inputs."""
        assert ContentCleaner.strip_previous_response("", "prev") == ""
        assert ContentCleaner.strip_previous_response("content", "") == "content"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

