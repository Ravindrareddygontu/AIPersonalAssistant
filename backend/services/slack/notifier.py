"""
Slack Notifier Service - Sends status notifications to Slack via webhook.

This service sends concise 2-3 line summaries after chat completion:
- Success: what was accomplished
- Failure: what went wrong
- Stopped: why it was interrupted

Summaries are generated using Auggie AI in a background thread.
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
        return self._send_webhook(message)

    def _format_message(self, notif: SlackNotification) -> str:
        """Format notification into Slack message."""
        # Truncate question if too long
        question = notif.question
        if len(question) > 100:
            question = question[:97] + "..."

        # Build message based on status
        if notif.status == CompletionStatus.SUCCESS:
            emoji = "✅"
            status_text = "Completed"
            lines = [
                f"{emoji} *{status_text}*: {question}",
                f"📝 {notif.summary}"
            ]
            if notif.execution_time:
                lines.append(f"⏱️ _{notif.execution_time:.1f}s_")

        elif notif.status == CompletionStatus.FAILURE:
            emoji = "❌"
            status_text = "Failed"
            lines = [
                f"{emoji} *{status_text}*: {question}",
                f"💥 {notif.error or notif.summary or 'Unknown error'}"
            ]

        elif notif.status == CompletionStatus.STOPPED:
            emoji = "⏹️"
            status_text = "Stopped"
            lines = [
                f"{emoji} *{status_text}*: {question}",
                f"🛑 {notif.summary or 'User interrupted the request'}"
            ]

        else:
            lines = [f"❓ *Unknown status*: {question}"]

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


def _generate_ai_summary(content: str, question: str, workspace: str) -> str:
    """
    Use a dedicated Auggie process to generate a human-readable summary.
    Creates an isolated process, gets the summary, then kills it.
    Returns a 2-3 line English summary of what was accomplished.
    """
    import os
    import pty
    import time
    import select
    import signal
    from backend.utils.text import TextCleaner

    if not content or len(content) < 50:
        return content[:200] if content else "Task completed"

    # Truncate content if too long for summarization
    truncated_content = content[:1500] if len(content) > 1500 else content

    # Escape special characters for the prompt
    escaped_content = truncated_content.replace('"', '\\"').replace('`', '\\`')

    # Create a summarization prompt
    prompt = f'Summarize in 2-3 short plain English sentences what was accomplished. No code or commands. Just the outcome: {escaped_content[:800]}'

    master_fd = None
    pid = None

    try:
        # Create a new PTY for isolated auggie process
        pid, master_fd = pty.fork()

        if pid == 0:
            # Child process - exec auggie
            os.chdir(workspace)
            os.execvp('auggie', ['auggie'])

        # Parent process - communicate with auggie
        log.info("[SLACK] Started isolated auggie process for summarization")

        # Wait for auggie to be ready (look for prompt)
        start = time.time()
        output = ""
        ready = False

        while time.time() - start < 30:  # 30s timeout for startup
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(master_fd, 4096).decode('utf-8', errors='ignore')
                    output += chunk
                    # Look for the input prompt
                    if '>' in TextCleaner.strip_ansi(output) or '●' in output:
                        ready = True
                        break
                except (OSError, IOError):
                    break

        if not ready:
            log.warning("[SLACK] Auggie not ready for summarization")
            return _fallback_summary(content)

        # Send the prompt
        os.write(master_fd, (prompt + '\n').encode('utf-8'))

        # Read the response
        output = ""
        start = time.time()
        last_data = time.time()

        while time.time() - start < 60:  # 60s max for response
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(master_fd, 4096).decode('utf-8', errors='ignore')
                    if chunk:
                        output += chunk
                        last_data = time.time()
                except (OSError, IOError):
                    break

            # Check for completion (silence after getting data)
            if output and time.time() - last_data > 3:
                break

        # Extract the summary from output
        clean = TextCleaner.strip_ansi(output)

        # Find the response after the prompt echo
        lines = clean.split('\n')
        summary_lines = []
        found_prompt = False

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip the echoed prompt
            if 'Summarize' in line or 'accomplished' in line:
                found_prompt = True
                continue
            # Skip UI elements
            if any(skip in line for skip in ['●', '>', '~', '⎿', '│', '─']):
                continue
            if found_prompt and line and len(line) > 10:
                summary_lines.append(line)
                if len(summary_lines) >= 3:
                    break

        if summary_lines:
            summary = ' '.join(summary_lines)
            if len(summary) > 300:
                summary = summary[:297] + "..."
            log.info(f"[SLACK] AI summary generated: {summary[:100]}...")
            return summary
        else:
            log.warning("[SLACK] Could not extract summary from auggie response")
            return _fallback_summary(content)

    except Exception as e:
        log.error(f"[SLACK] Error generating AI summary: {e}")
        return _fallback_summary(content)
    finally:
        # Kill the auggie process
        if pid and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, os.WNOHANG)
                log.info("[SLACK] Killed summarization auggie process")
            except (OSError, ProcessLookupError):
                pass
        if master_fd:
            try:
                os.close(master_fd)
            except OSError:
                pass


def _fallback_summary(content: str) -> str:
    """Fallback to simple pattern-based summary."""
    from backend.services.auggie import ResponseSummarizer
    return ResponseSummarizer.summarize(content, max_length=200)


def _send_notification_thread(
    question: str,
    content: str,
    success: bool,
    error: Optional[str],
    stopped: bool,
    execution_time: Optional[float],
    webhook_url: str,
    workspace: str
):
    """
    Background thread to generate summary and send Slack notification.
    Uses Auggie for AI-powered summarization, then cleans up.
    """
    try:
        # Determine status and generate summary
        if stopped:
            status = CompletionStatus.STOPPED
            summary = "Request was interrupted by user"
        elif not success or error:
            status = CompletionStatus.FAILURE
            summary = error or "Request failed"
        else:
            status = CompletionStatus.SUCCESS
            # Use AI to generate a proper English summary
            summary = _generate_ai_summary(content, question, workspace)

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

    Uses Auggie AI to generate a proper English summary.
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
            settings.slack_webhook_url,
            settings.workspace
        ),
        daemon=True
    )
    thread.start()

    log.info("[SLACK] Notification thread started")
    return True

