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
    question: str
    status: CompletionStatus
    summary: str
    error: Optional[str] = None
    execution_time: Optional[float] = None


class SlackNotifier:

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith('https://hooks.slack.com/'))

    def notify(self, notification: SlackNotification) -> bool:
        if not self.is_configured():
            log.warning("[SLACK] Webhook URL not configured")
            return False

        message = self._format_message(notification)
        log.info(f"[SLACK] Sending message: {message[:200]}")
        return self._send_webhook(message)

    def _format_message(self, notif: SlackNotification) -> str:
        question = notif.question
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
    if not content:
        return "Task completed"

    # Import shared constant for command indicators (reduces duplication)
    from backend.config import TERMINAL_COMMAND_INDICATORS

    # Special characters that indicate non-summary lines
    SPECIAL_LINE_PREFIXES = '↳>$#│─╭╰●⎿'
    MIN_LINE_LENGTH = 10
    MIN_ALPHA_RATIO = 0.6  # At least 60% letters/spaces for English text
    MAX_SUMMARY_LENGTH = 200

    lines = content.split('\n')
    for line in lines:
        line = line.strip()

        # Skip empty or very short lines
        if not line or len(line) < MIN_LINE_LENGTH:
            continue

        # Skip command-like lines using shared constant
        if any(indicator in line for indicator in TERMINAL_COMMAND_INDICATORS):
            continue

        # Skip lines starting with special chars (terminal markers)
        if line[0] in SPECIAL_LINE_PREFIXES:
            continue

        # Check if it's mostly English text (letters and spaces)
        alpha_count = sum(1 for c in line if c.isalpha() or c.isspace())
        if alpha_count < len(line) * MIN_ALPHA_RATIO:
            continue

        # Found a good summary line
        return line[:MAX_SUMMARY_LENGTH]

    # Fallback: use pattern-based summarizer
    from backend.services.auggie import ResponseSummarizer
    return ResponseSummarizer.summarize(content, max_length=MAX_SUMMARY_LENGTH)


def _send_notification_thread(
    question: str,
    content: str,
    success: bool,
    error: Optional[str],
    stopped: bool,
    execution_time: Optional[float],
    webhook_url: str
):
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

