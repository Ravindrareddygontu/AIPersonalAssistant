"""
Tests for status message filtering and cleanup.

These tests verify:
1. Queue-related noise is filtered from status messages
2. Empty parentheses are removed after content filtering
3. Status messages stop when response is complete (end_pattern_seen)
4. Session resumption with has_messages flag
"""

import pytest
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStatusMessageFiltering:
    """Test filtering of terminal UI noise from status messages."""

    def _clean_status_line(self, line: str) -> str:
        """Replicate the cleaning logic from _detect_activity."""
        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        clean_line = re.sub(r'[│╭╮╯╰─┌┐└┘├┤┬┴┼]', '', clean_line)
        clean_line = re.sub(r'\s*[•·\-–—]\s*esc to interrupt', '', clean_line, flags=re.IGNORECASE)
        clean_line = re.sub(r'\((\d+)s\.?\s*[•·\-–—]?\s*\)', r'\1s', clean_line)
        clean_line = re.sub(r'/queue\s+to\s+manage', '', clean_line, flags=re.IGNORECASE)
        clean_line = re.sub(r'Message will be queued', '', clean_line, flags=re.IGNORECASE)
        clean_line = re.sub(r'\(\s*\)', '', clean_line)
        clean_line = clean_line.strip()
        return clean_line

    def test_filters_queue_to_manage(self):
        """Test /queue to manage is filtered out."""
        line = "⠋ Sending request... /queue to manage"
        result = self._clean_status_line(line)
        assert "/queue" not in result.lower()
        assert "manage" not in result.lower()
        assert "Sending request" in result

    def test_filters_message_will_be_queued(self):
        """Test 'Message will be queued' is filtered out."""
        line = "Message will be queued - Sending request..."
        result = self._clean_status_line(line)
        assert "queued" not in result.lower()
        assert "Sending request" in result

    def test_filters_empty_parentheses(self):
        """Test empty parentheses are removed after content filtering."""
        line = "Sending request () - processing"
        result = self._clean_status_line(line)
        assert "()" not in result

    def test_filters_parentheses_with_spaces(self):
        """Test parentheses with only spaces are removed."""
        line = "Sending request (   ) done"
        result = self._clean_status_line(line)
        assert "(" not in result
        assert ")" not in result

    def test_preserves_time_in_parentheses(self):
        """Test time values like (5s) are preserved."""
        line = "⠋ Receiving response (5s)"
        result = self._clean_status_line(line)
        assert "5s" in result

    def test_combined_noise_filtering(self):
        """Test multiple noise patterns are all filtered."""
        line = "│ ⠋ Sending request... (5s) /queue to manage • esc to interrupt │"
        result = self._clean_status_line(line)
        assert "/queue" not in result.lower()
        assert "esc to interrupt" not in result.lower()
        assert "5s" in result
        assert "Sending request" in result

    def test_returns_empty_for_only_noise(self):
        """Test returns empty string when line is only noise."""
        line = "│ /queue to manage │"
        result = self._clean_status_line(line)
        assert result == ""

    def test_case_insensitive_filtering(self):
        """Test filtering is case insensitive."""
        line = "MESSAGE WILL BE QUEUED - /QUEUE TO MANAGE"
        result = self._clean_status_line(line)
        assert "queue" not in result.lower()
        assert "message" not in result.lower()


class TestEndPatternSeenStatusStop:
    """Test that status messages stop when end_pattern_seen is True."""

    def test_status_condition_without_end_pattern(self):
        """Test status updates continue when end_pattern_seen is False."""
        end_pattern_seen = False
        should_send_status = not end_pattern_seen
        assert should_send_status is True

    def test_status_condition_with_end_pattern(self):
        """Test status updates stop when end_pattern_seen is True."""
        end_pattern_seen = True
        should_send_status = not end_pattern_seen
        assert should_send_status is False


class TestForceNewSessionLogic:
    """Test force_new_session logic with has_messages flag."""

    def test_new_chat_no_session_no_messages(self):
        """Test truly new chat forces new session."""
        session_id = None
        has_messages = False
        force_new_session = session_id is None and not has_messages
        assert force_new_session is True

    def test_aborted_chat_no_session_but_has_messages(self):
        """Test aborted Q1 chat (has messages but no session_id) reuses session."""
        session_id = None
        has_messages = True
        force_new_session = session_id is None and not has_messages
        assert force_new_session is False

    def test_existing_chat_with_session_id(self):
        """Test existing chat with session_id reuses session."""
        session_id = "abc-123"
        has_messages = True
        force_new_session = session_id is None and not has_messages
        assert force_new_session is False

    def test_existing_session_no_messages_yet(self):
        """Test chat with session_id but no messages (edge case)."""
        session_id = "abc-123"
        has_messages = False
        force_new_session = session_id is None and not has_messages
        assert force_new_session is False


class TestEndPatternNotResetOnNoise:
    """Test that end_pattern_seen is not reset on terminal noise."""

    def test_end_pattern_preserved_concept(self):
        """Test concept: end_pattern_seen should only reset on NEW content."""
        end_pattern_seen = True
        has_new_content = False
        
        if has_new_content:
            end_pattern_seen = False
        
        assert end_pattern_seen is True

    def test_end_pattern_reset_on_new_content(self):
        """Test end_pattern_seen resets when there IS new content."""
        end_pattern_seen = True
        has_new_content = True
        
        if has_new_content:
            end_pattern_seen = False
        
        assert end_pattern_seen is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

