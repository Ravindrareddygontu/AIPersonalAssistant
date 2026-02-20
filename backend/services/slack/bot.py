import os
import re
import logging
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field

log = logging.getLogger('slack.bot')


@dataclass
class SlackBotConfig:
    bot_token: str = None           # xoxb-... Bot User OAuth Token
    app_token: str = None           # xapp-... App-Level Token (for Socket Mode)
    signing_secret: str = None      # For verifying requests (Events API mode)
    workspace: str = None           # Default workspace for Auggie
    model: str = None               # Default model for Auggie
    
    def __post_init__(self):
        self.bot_token = self.bot_token or os.environ.get('SLACK_BOT_TOKEN')
        self.app_token = self.app_token or os.environ.get('SLACK_APP_TOKEN')
        self.signing_secret = self.signing_secret or os.environ.get('SLACK_SIGNING_SECRET')
        self.workspace = self.workspace or os.environ.get(
            'SLACK_WORKSPACE',
            os.path.expanduser("~/Projects/POC'S/ai-chat-app")
        )
        self.model = self.model or os.environ.get('SLACK_MODEL')
    
    @property
    def is_socket_mode(self) -> bool:
        return bool(self.app_token and self.app_token.startswith('xapp-'))


class SlackBot:

    def __init__(self, config: SlackBotConfig = None):
        self.config = config or SlackBotConfig()
        self._app = None
        self._handler = None
        self._executor = None
        self._summarizer = None
        self._ai_summarizer = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def _ensure_initialized(self):
        if self._app is not None:
            return
        
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError:
            raise ImportError("Run: pip install slack-bolt")
        
        # Initialize Slack Bolt app
        self._app = App(
            token=self.config.bot_token,
            signing_secret=self.config.signing_secret,
        )
        
        from backend.services.auggie import AuggieExecutor, ResponseSummarizer
        from backend.services.auggie.summarizer import AISummarizer
        self._executor = AuggieExecutor()
        self._summarizer = ResponseSummarizer
        self._ai_summarizer = AISummarizer

        self._register_handlers()

        log.info("[SLACK BOT] Initialized")
    
    def _register_handlers(self):

        @self._app.event("app_mention")
        def handle_mention(event, say, client):
            self._handle_message(event, say, client)

        @self._app.event("message")
        def handle_message(event, say, client):
            channel_type = event.get("channel_type")
            if channel_type == "im":
                if event.get("bot_id"):
                    return
                self._handle_message(event, say, client)

        @self._app.command("/auggie")
        def handle_slash_command(ack, respond, command):
            ack()
            self._handle_slash_command(respond, command)
        
        log.info("[SLACK BOT] Event handlers registered")
    
    def _extract_message_text(self, event: dict) -> str:
        text = event.get("text", "")
        # Remove bot mention if present
        text = re.sub(r'<@[A-Z0-9]+>\s*', '', text).strip()
        return text
    
    def _handle_message(self, event: dict, say: Callable, client):
        text = self._extract_message_text(event)
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")

        if not text:
            say("Please provide a message!", thread_ts=thread_ts)
            return

        log.info(f"[SLACK BOT] Processing: {text[:50]}...")
        log.info(f"[SLACK BOT] Channel: {channel}, Thread: {thread_ts}")

        # Send thinking indicator
        say("⏳ Working on it...", thread_ts=thread_ts)

        # Execute via Auggie
        try:
            log.info(f"[SLACK BOT] Executing with workspace: {self.config.workspace}")
            response = self._executor.execute(
                message=text,
                workspace=self.config.workspace,
                model=self.config.model
            )

            log.info(f"[SLACK BOT] Response received - success: {response.success}, "
                     f"content_len: {len(response.content) if response.content else 0}, "
                     f"error: {response.error}, time: {response.execution_time:.1f}s")

            if response.success:
                content = response.content or ""

                log.info(f"[SLACK BOT] Content preview: {repr(content[:500])}")

                if len(content) > 2900:
                    summary = self._summarizer.summarize(content)
                    reply = f"{content[:2500]}\n\n... _(truncated)_\n\n📝 *Summary:* {summary}\n\n⏱️ _{response.execution_time:.1f}s_"
                else:
                    reply = f"{content}\n\n⏱️ _{response.execution_time:.1f}s_"

                log.info(f"[SLACK BOT] Reply length: {len(reply)} chars")
            else:
                reply = f"❌ Error: {response.error}"
                log.error(f"[SLACK BOT] Execution failed: {response.error}")

            log.info(f"[SLACK BOT] Sending reply to Slack...")
            say(reply, thread_ts=thread_ts)
            log.info(f"[SLACK BOT] ✅ Reply sent successfully ({len(reply)} chars)")

            if response.success and content:
                self._send_ai_summary(text, content, say, thread_ts)

        except Exception as e:
            log.exception(f"[SLACK BOT] Execution error: {e}")
            say(f"❌ Error: {str(e)}", thread_ts=thread_ts)

    def _handle_slash_command(self, respond: Callable, command: dict):
        text = command.get("text", "").strip()
        user = command.get("user_name", "user")
        channel = command.get("channel_id", "unknown")

        # Handle help command
        if not text or text.lower() == "help":
            respond(self._get_help_text())
            return

        # Handle status command
        if text.lower() == "status":
            respond(f"🤖 Auggie Bot is running\n📁 Workspace: `{self.config.workspace}`")
            return

        log.info(f"[SLACK BOT] Slash command from {user} in {channel}: {text[:50]}...")

        # Send acknowledgment
        respond("⏳ Processing your request...")

        # Execute via Auggie
        try:
            log.info(f"[SLACK BOT] Executing slash command with workspace: {self.config.workspace}")
            response = self._executor.execute(
                message=text,
                workspace=self.config.workspace,
                model=self.config.model
            )

            log.info(f"[SLACK BOT] Slash response - success: {response.success}, "
                     f"content_len: {len(response.content) if response.content else 0}, "
                     f"error: {response.error}, time: {response.execution_time:.1f}s")

            if response.success:
                content = response.content or ""

                log.info(f"[SLACK BOT] Content preview: {repr(content[:500])}")

                if len(content) > 2900:
                    summary = self._summarizer.summarize(content)
                    content = f"{content[:2500]}\n\n... _(truncated)_\n\n📝 *Summary:* {summary}"

                reply = f"✅ *Result:*\n{content}\n\n⏱️ _{response.execution_time:.1f}s_"
                log.info(f"[SLACK BOT] Slash reply length: {len(reply)} chars")
            else:
                reply = f"❌ *Error:* {response.error}"
                log.error(f"[SLACK BOT] Slash execution failed: {response.error}")

            log.info(f"[SLACK BOT] Sending slash reply...")
            respond(reply)
            log.info(f"[SLACK BOT] ✅ Slash reply sent successfully")

            if response.success and content:
                self._send_ai_summary_respond(text, content, respond)

        except Exception as e:
            log.exception(f"[SLACK BOT] Slash command error: {e}")
            respond(f"❌ Error: {str(e)}")

    def _send_ai_summary(self, question: str, answer: str, say: Callable, thread_ts: str):
        try:
            log.info("[SLACK BOT] Generating AI summary...")
            summary = self._ai_summarizer.summarize(question, answer, max_points=3)

            if summary:
                summary_msg = f"📋 *AI Summary (3 key points):*\n{summary}"
                say(summary_msg, thread_ts=thread_ts)
                log.info("[SLACK BOT] ✅ AI summary sent")
            else:
                log.info("[SLACK BOT] AI summary skipped (no API key or error)")
        except Exception as e:
            log.error(f"[SLACK BOT] AI summary failed: {e}")

    def _send_ai_summary_respond(self, question: str, answer: str, respond: Callable):
        try:
            log.info("[SLACK BOT] Generating AI summary for slash command...")
            summary = self._ai_summarizer.summarize(question, answer, max_points=3)

            if summary:
                summary_msg = f"📋 *AI Summary (3 key points):*\n{summary}"
                respond(summary_msg)
                log.info("[SLACK BOT] ✅ AI summary sent")
            else:
                log.info("[SLACK BOT] AI summary skipped (no API key or error)")
        except Exception as e:
            log.error(f"[SLACK BOT] AI summary failed: {e}")

    def _get_help_text(self) -> str:
        return """🤖 *Auggie Bot - AI Code Assistant*

*Slash Commands:*
• `/auggie <question>` - Ask Auggie anything
• `/auggie help` - Show this help message
• `/auggie status` - Check bot status

*Direct Message:*
• Send me a DM with your question

*Mention:*
• @Auggie <question> - Mention me in any channel

*Examples:*
• `/auggie list all Python files in src/`
• `/auggie explain the main function in app.py`
• `/auggie what does this project do?`
"""

    @property
    def app(self):
        self._ensure_initialized()
        return self._app

    def start_socket_mode(self, blocking: bool = True):
        if not self.config.is_socket_mode:
            raise ValueError("Socket Mode requires SLACK_APP_TOKEN (xapp-...)")

        self._ensure_initialized()

        from slack_bolt.adapter.socket_mode import SocketModeHandler
        self._handler = SocketModeHandler(self._app, self.config.app_token)

        log.info("[SLACK BOT] Starting in Socket Mode...")
        self._running = True

        if blocking:
            self._handler.start()
        else:
            self._thread = threading.Thread(target=self._handler.start, daemon=True)
            self._thread.start()
            log.info("[SLACK BOT] Socket Mode started in background")

    def stop(self):
        self._running = False
        if self._handler:
            self._handler.close()
        log.info("[SLACK BOT] Stopped")


# Convenience function for creating a configured bot
def create_slack_bot(
    bot_token: str = None,
    app_token: str = None,
    workspace: str = None,
    model: str = None
) -> SlackBot:
    config = SlackBotConfig(
        bot_token=bot_token,
        app_token=app_token,
        workspace=workspace,
        model=model
    )
    return SlackBot(config)

