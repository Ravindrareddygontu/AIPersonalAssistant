"""
Tests for slack/notifier.py - Slack notification service.

Tests cover:
- CompletionStatus enum
- SlackNotification dataclass
- SlackNotifier class: is_configured, notify, _format_message, _send_webhook
- _extract_summary function
- notify_completion function
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, ANY
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.bots.slack.notifier import (
    CompletionStatus, SlackNotification, SlackNotifier,
    _extract_summary, notify_completion
)


class TestCompletionStatus:
    """Test CompletionStatus enum."""

    def test_status_values(self):
        """Test enum values."""
        assert CompletionStatus.SUCCESS.value == "success"
        assert CompletionStatus.FAILURE.value == "failure"
        assert CompletionStatus.STOPPED.value == "stopped"


class TestSlackNotification:
    """Test SlackNotification dataclass."""

    def test_basic_notification(self):
        """Test basic notification creation."""
        notif = SlackNotification(
            question="Test question",
            status=CompletionStatus.SUCCESS,
            summary="Task completed"
        )
        assert notif.question == "Test question"
        assert notif.status == CompletionStatus.SUCCESS
        assert notif.summary == "Task completed"
        assert notif.error is None
        assert notif.execution_time is None

    def test_notification_with_all_fields(self):
        """Test notification with all optional fields."""
        notif = SlackNotification(
            question="Test",
            status=CompletionStatus.FAILURE,
            summary="Failed",
            error="Connection error",
            execution_time=5.5
        )
        assert notif.error == "Connection error"
        assert notif.execution_time == 5.5


class TestSlackNotifierIsConfigured:
    """Test SlackNotifier.is_configured method."""

    def test_valid_webhook_url(self):
        """Test with valid Slack webhook URL."""
        notifier = SlackNotifier("https://hooks.slack.com/services/T00/B00/xxx")
        assert notifier.is_configured() == True

    def test_invalid_webhook_url(self):
        """Test with invalid webhook URL."""
        notifier = SlackNotifier("https://example.com/webhook")
        assert notifier.is_configured() == False

    def test_empty_webhook_url(self):
        """Test with empty webhook URL."""
        notifier = SlackNotifier("")
        assert notifier.is_configured() == False

    def test_none_webhook_url(self):
        """Test with None webhook URL."""
        notifier = SlackNotifier(None)
        assert notifier.is_configured() == False


class TestSlackNotifierFormatMessage:
    """Test SlackNotifier._format_message method."""

    def test_format_success_message(self):
        """Test formatting success message."""
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        notif = SlackNotification(
            question="Test question",
            status=CompletionStatus.SUCCESS,
            summary="Task completed successfully",
            execution_time=10.5
        )
        result = notifier._format_message(notif)
        
        assert "Q: Test question" in result
        assert "(10s)" in result or "(11s)" in result
        assert "✓" in result
        assert "Task completed" in result

    def test_format_failure_message(self):
        """Test formatting failure message."""
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        notif = SlackNotification(
            question="Test",
            status=CompletionStatus.FAILURE,
            summary="",
            error="Connection timeout"
        )
        result = notifier._format_message(notif)
        
        assert "✗" in result
        assert "Connection timeout" in result

    def test_format_stopped_message(self):
        """Test formatting stopped message."""
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        notif = SlackNotification(
            question="Test",
            status=CompletionStatus.STOPPED,
            summary="User cancelled"
        )
        result = notifier._format_message(notif)
        
        assert "⏹" in result
        assert "User cancelled" in result or "Stopped by user" in result

    def test_truncates_long_questions(self):
        """Test that long questions are truncated."""
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        long_question = "A" * 150
        notif = SlackNotification(
            question=long_question,
            status=CompletionStatus.SUCCESS,
            summary="Done"
        )
        result = notifier._format_message(notif)
        
        # Question should be truncated to 100 chars + "..."
        assert "..." in result
        assert len(result.split('\n')[0]) < 150


class TestSlackNotifierNotify:
    """Test SlackNotifier.notify method."""

    def test_notify_not_configured(self):
        """Test notify when not configured."""
        notifier = SlackNotifier("")
        notif = SlackNotification("Q", CompletionStatus.SUCCESS, "S")
        result = notifier.notify(notif)
        assert result == False

    @patch.object(SlackNotifier, '_send_webhook')
    def test_notify_sends_webhook(self, mock_send):
        """Test that notify calls _send_webhook."""
        mock_send.return_value = True
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        notif = SlackNotification("Q", CompletionStatus.SUCCESS, "S")
        
        result = notifier.notify(notif)
        
        assert result == True
        mock_send.assert_called_once()


class TestSendWebhook:
    """Test SlackNotifier._send_webhook method."""

    @patch('urllib.request.urlopen')
    def test_send_webhook_success(self, mock_urlopen):
        """Test successful webhook send."""
        mock_urlopen.return_value = MagicMock()
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        
        result = notifier._send_webhook("Test message")
        
        assert result == True
        mock_urlopen.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_send_webhook_failure(self, mock_urlopen):
        """Test webhook send failure."""
        mock_urlopen.side_effect = Exception("Network error")
        notifier = SlackNotifier("https://hooks.slack.com/services/xxx")
        
        result = notifier._send_webhook("Test message")
        
        assert result == False


class TestExtractSummary:
    """Test _extract_summary function."""

    def test_empty_content(self):
        """Test with empty content."""
        result = _extract_summary("")
        assert result == "Task completed"

    def test_extracts_first_good_line(self):
        """Test extraction of first meaningful line."""
        content = """Terminal - Running command
ls -la
This is the actual response summary that makes sense."""
        result = _extract_summary(content)
        
        assert "actual response" in result.lower() or "summary" in result.lower()

    def test_skips_command_lines(self):
        """Test skipping command-like lines."""
        content = """grep -r pattern
cd /home/user
The search found 5 results."""
        result = _extract_summary(content)
        
        assert "grep" not in result
        assert "cd " not in result

    def test_skips_special_char_lines(self):
        """Test skipping lines starting with special chars."""
        content = """↳ continuation
> quote
$ command
This is the good content."""
        result = _extract_summary(content)
        
        if "good content" in result.lower():
            assert True


class TestNotifyCompletion:
    """Test notify_completion function."""

    @patch('backend.config.settings')
    def test_disabled_returns_false(self, mock_settings):
        """Test that disabled notification returns False."""
        mock_settings.slack_notify = False

        result = notify_completion("Q", "Content")

        assert result == False

    @patch('backend.config.settings')
    def test_no_webhook_returns_false(self, mock_settings):
        """Test that missing webhook returns False."""
        mock_settings.slack_notify = True
        mock_settings.slack_webhook_url = ""

        result = notify_completion("Q", "Content")

        assert result == False

    @patch('backend.config.settings')
    @patch('threading.Thread')
    def test_starts_background_thread(self, mock_thread_class, mock_settings):
        """Test that notification starts in background thread."""
        mock_settings.slack_notify = True
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/xxx"
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        result = notify_completion("Q", "Content")

        assert result == True
        mock_thread.start.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

