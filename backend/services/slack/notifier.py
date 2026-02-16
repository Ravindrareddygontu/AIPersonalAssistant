"""
Slack Notifier Service - Sends status notifications to Slack via webhook.

This service sends concise 2-3 line summaries after chat completion:
- Success: what was accomplished
- Failure: what went wrong
- Stopped: why it was interrupted

Summaries are generated using pattern-based analysis in a background thread.
"""

import json
import logging
import threading
import urllib.request
from typing import Optional
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger('slack.notifier')


class CompletionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    STOPPED = "stopped"


@dataclass
class SlackNotification:
    """Represents a Slack notification to be sent."""
    question: str
    status: CompletionStatus
    summary: str
    error: Optional[str] = None
    execution_time: Optional[float] = None


class SlackNotifier:
    """Sends chat completion notifications to Slack via webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        """Check if webhook URL is configured."""
        return bool(self.webhook_url and self.webhook_url.startswith('https://hooks.slack.com/'))

    def notify(self, notification: SlackNotification) -> bool:
        """
        Send a notification to Slack.
        
        Returns True if successful, False otherwise.
        """
        if not self.is_configured():
            log.warning("[SLACK] Webhook URL not configured")
            return False

        message = self._format_message(notification)
        log.info(f"[SLACK] Sending message: {message[:200]}")
        return self._send_webhook(message)

    def _format_message(self, notif: SlackNotification) -> str:
        """Format notification into Slack message."""
        # Truncate question if too long
        question = notif.question
        if len(question) > 100:
            question = question[:97] + "..."

        # Build message based on status - minimal format
        time_str = f" ({notif.execution_time:.0f}s)" if notif.execution_time else ""

        if notif.status == CompletionStatus.SUCCESS:
            lines = [
                f"Q: {question}{time_str}",
                f"✓ {notif.summary}"
            ]

        elif notif.status == CompletionStatus.FAILURE:
            lines = [
                f"Q: {question}",
                f"✗ {notif.error or notif.summary or 'Failed'}"
            ]

        elif notif.status == CompletionStatus.STOPPED:
            lines = [
                f"Q: {question}",
                f"⏹ {notif.summary or 'Stopped by user'}"
            ]

        else:
            lines = [f"Q: {question}"]

        return "\n".join(lines)

    def _send_webhook(self, message: str) -> bool:
        """Send message to Slack webhook."""
        try:
            data = json.dumps({"text": message}).encode('utf-8')
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            log.info("[SLACK] Notification sent successfully")
            return True
        except Exception as e:
            log.error(f"[SLACK] Failed to send notification: {e}")
            return False


def _extract_summary(content: str) -> str:
    """
    Extract a short summary from the already-cleaned chat content.
    The content is already cleaned by the frontend pipeline, so we just
    need to get the first meaningful sentence.
    """
    if not content:
        return "Task completed"

    # Skip patterns that indicate commands/terminal output
    skip_indicators = [
        'Terminal -', '2>/dev/null', '||', '&&', 'grep ', 'lsof ',
        'netstat ', 'ps aux', 'cd ', '$ ', '# ', '```'
    ]

    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        # Skip command-like lines
        if any(indicator in line for indicator in skip_indicators):
            continue
        # Skip lines starting with special chars
        if line[0] in '↳>$#│─╭╰●⎿':
            continue
        # Check if it's mostly English (at least 60% letters/spaces)
        alpha_count = sum(1 for c in line if c.isalpha() or c.isspace())
        if alpha_count < len(line) * 0.6:
            continue
        # Found a good line
        return line[:200]

    # Fallback: use pattern-based summarizer
    from backend.services.auggie import ResponseSummarizer
    return ResponseSummarizer.summarize(content, max_length=200)


def _send_notification_thread(
    question: str,
    content: str,
    success: bool,
    error: Optional[str],
    stopped: bool,
    execution_time: Optional[float],
    webhook_url: str
):
    """
    Background thread to generate summary and send Slack notification.
    Extracts summary from already-cleaned content.
    """
    try:
        # Determine status and generate summary
        if stopped:
            status = CompletionStatus.STOPPED
            summary = "Stopped by user"
        elif not success or error:
            status = CompletionStatus.FAILURE
            summary = error or "Request failed"
        else:
            status = CompletionStatus.SUCCESS
            # Extract summary from already-cleaned content
            summary = _extract_summary(content)
            log.info(f"[SLACK] Extracted summary: {summary}")

        notification = SlackNotification(
            question=question,
            status=status,
            summary=summary,
            error=error,
            execution_time=execution_time
        )

        notifier = SlackNotifier(webhook_url)
        notifier.notify(notification)

    except Exception as e:
        log.error(f"[SLACK] Notification thread error: {e}")


def notify_completion(
    question: str,
    content: str,
    success: bool = True,
    error: Optional[str] = None,
    stopped: bool = False,
    execution_time: Optional[float] = None
) -> bool:
    """
    Send a completion notification to Slack in a background thread.

    Extracts summary from already-cleaned content (no extra auggie call needed).
    Runs in background so it doesn't block the main response.
    """
    from backend.config import settings

    if not settings.slack_notify:
        return False

    if not settings.slack_webhook_url:
        log.warning("[SLACK] Notifications enabled but no webhook URL configured")
        return False

    # Run notification in background thread
    thread = threading.Thread(
        target=_send_notification_thread,
        args=(
            question,
            content,
            success,
            error,
            stopped,
            execution_time,
            settings.slack_webhook_url
        ),
        daemon=True
    )
    thread.start()

    log.info("[SLACK] Notification thread started")
    return True

