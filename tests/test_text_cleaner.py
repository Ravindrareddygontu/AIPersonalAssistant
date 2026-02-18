"""
Tests for text.py - TextCleaner class for ANSI stripping and response cleaning.

Tests cover:
- strip_ansi: Removing ANSI escape codes
- clean_response: Cleaning response text of UI elements
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.text import TextCleaner


class TestStripAnsi:
    """Test ANSI escape code stripping."""

    def test_no_ansi_codes(self):
        """Test text without ANSI codes is unchanged."""
        text = "Simple text without codes"
        result = TextCleaner.strip_ansi(text)
        assert result == text

    def test_color_codes(self):
        """Test stripping common color codes."""
        # ESC[31m = red, ESC[0m = reset
        text = "\x1b[31mRed text\x1b[0m"
        result = TextCleaner.strip_ansi(text)
        assert result == "Red text"

    def test_multiple_codes(self):
        """Test stripping multiple ANSI codes."""
        text = "\x1b[1m\x1b[32mBold green\x1b[0m and \x1b[34mblue\x1b[0m"
        result = TextCleaner.strip_ansi(text)
        assert result == "Bold green and blue"

    def test_cursor_codes(self):
        """Test stripping cursor movement codes."""
        text = "\x1b[2JScreen cleared\x1b[H"
        result = TextCleaner.strip_ansi(text)
        assert "Screen cleared" in result

    def test_sgr_parameters(self):
        """Test stripping SGR (Select Graphic Rendition) codes."""
        text = "\x1b[38;5;196mColored\x1b[0m"
        result = TextCleaner.strip_ansi(text)
        assert "Colored" in result

    def test_extra_patterns(self):
        """Test stripping extra patterns like RGB color specs."""
        text = "Text 38;2;255;0;0 more text"
        result = TextCleaner.strip_ansi(text)
        assert "38;2;255" not in result

    def test_processing_messages(self):
        """Test stripping processing status messages."""
        text = "Response Processing response... (2.5s) more text"
        result = TextCleaner.strip_ansi(text)
        assert "Processing response" not in result

    def test_esc_to_interrupt(self):
        """Test stripping 'esc to interrupt' messages."""
        text = "Content (esc to interrupt) more"
        result = TextCleaner.strip_ansi(text)
        assert "esc to interrupt" not in result

    def test_braille_characters(self):
        """Test stripping braille spinner characters."""
        text = "Loading ⠋ text"
        result = TextCleaner.strip_ansi(text)
        assert "⠋" not in result

    def test_empty_string(self):
        """Test handling empty string."""
        result = TextCleaner.strip_ansi("")
        assert result == ""

    def test_multiline_text(self):
        """Test stripping ANSI from multiline text."""
        text = "\x1b[31mLine 1\x1b[0m\n\x1b[32mLine 2\x1b[0m"
        result = TextCleaner.strip_ansi(text)
        assert result == "Line 1\nLine 2"


class TestCleanResponse:
    """Test response cleaning."""

    def test_simple_text(self):
        """Test that simple text passes through."""
        text = "This is a simple response."
        result = TextCleaner.clean_response(text)
        assert result == "This is a simple response."

    def test_removes_box_characters(self):
        """Test removing box drawing characters."""
        text = "╭──────╮\n│ Text │\n╰──────╯"
        result = TextCleaner.clean_response(text)
        assert "╭" not in result
        assert "╯" not in result

    def test_removes_claude_markers(self):
        """Test removing [Claude...] markers."""
        text = "[Claude Opus] ~ Response text"
        result = TextCleaner.clean_response(text)
        assert "[Claude" not in result

    def test_removes_keyboard_shortcuts(self):
        """Test removing keyboard shortcut help."""
        text = "Response\nCtrl+S to save\nMore text"
        result = TextCleaner.clean_response(text)
        assert "Ctrl+S" not in result

    def test_removes_automation_hints(self):
        """Test removing automation hints."""
        text = "Response\nFor automation use auggie --print\nText"
        result = TextCleaner.clean_response(text)
        assert "automation" not in result.lower()

    def test_removes_copy_text(self):
        """Test removing standalone 'Copy' text."""
        text = "Code block\nCopy\nMore text"
        result = TextCleaner.clean_response(text)
        lines = [l.strip() for l in result.split('\n') if l.strip()]
        assert "Copy" not in lines

    def test_collapses_newlines(self):
        """Test that multiple newlines are collapsed."""
        text = "Line 1\n\n\n\n\nLine 2"
        result = TextCleaner.clean_response(text)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_removes_prompt_arrow(self):
        """Test removing prompt arrow at end."""
        text = "Response text\n› "
        result = TextCleaner.clean_response(text)
        assert result.rstrip() == "Response text"

    def test_removes_spinner_sending(self):
        """Test removing spinner with 'Sending request'."""
        text = "⠋ Sending request... response text"
        result = TextCleaner.clean_response(text)
        assert "Sending request" not in result

    def test_empty_string(self):
        """Test handling empty string."""
        result = TextCleaner.clean_response("")
        assert result == ""

    def test_preserves_code_content(self):
        """Test that actual code content is preserved."""
        text = "def hello():\n    print('world')\n    return True"
        result = TextCleaner.clean_response(text)
        assert "def hello():" in result
        assert "print('world')" in result

    def test_preserves_markdown(self):
        """Test that markdown formatting is preserved."""
        text = "# Header\n\n**Bold** and *italic*\n\n- List item"
        result = TextCleaner.clean_response(text)
        assert "# Header" in result
        assert "**Bold**" in result

    def test_combined_cleaning(self):
        """Test combined cleaning of various artifacts."""
        text = "╭────╮\nActual response\n╰────╯\nCtrl+P to enhance"
        result = TextCleaner.clean_response(text)
        assert "Actual response" in result
        assert "╭" not in result
        assert "Ctrl+P" not in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

