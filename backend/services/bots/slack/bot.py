import os
import re
import time
import logging
import threading
from typing import Optional, Callable
from dataclasses import dataclass

from backend.services.bots.base import BaseBot, BaseBotConfig
from backend.config import DEFAULT_WORKSPACE_PATH

log = logging.getLogger('slack.bot')


@dataclass
class SlackBotConfig(BaseBotConfig):
    app_token: str = None
    signing_secret: str = None

    def __post_init__(self):
        self.bot_token = self.bot_token or os.environ.get('SLACK_BOT_TOKEN')
        self.app_token = self.app_token or os.environ.get('SLACK_APP_TOKEN')
        self.signing_secret = self.signing_secret or os.environ.get('SLACK_SIGNING_SECRET')
        self.workspace = self.workspace or os.environ.get('SLACK_WORKSPACE', DEFAULT_WORKSPACE_PATH)
        self.model = self.model or os.environ.get('SLACK_MODEL')

    @property
    def is_socket_mode(self) -> bool:
        return bool(self.app_token and self.app_token.startswith('xapp-'))


class SlackBot(BaseBot):

    MAX_MESSAGE_LENGTH = 2900  # Slack limit is ~3000
    PLATFORM = "slack"

    def __init__(self, config: SlackBotConfig = None, repository=None):
        super().__init__(config or SlackBotConfig(), repository)
        self._app = None
        self._handler = None
        self._thread: Optional[threading.Thread] = None

    def _ensure_initialized(self):
        if self._app is not None:
            return

        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError:
            raise ImportError("Run: pip install slack-bolt")

        self._app = App(
            token=self.config.bot_token,
            signing_secret=self.config.signing_secret,
        )

        self._init_executor()

        if self._repository is None:
            from backend.services.bots.slack.bot_chat_repository import BotChatRepository
            self._repository = BotChatRepository()

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
    
    def _animate_executing(self, client, channel: str, ts: str, stop_event: threading.Event):
        idx = 1
        time.sleep(self.ANIMATION_INTERVAL)
        while not stop_event.is_set():
            try:
                client.chat_update(channel=channel, ts=ts, text=self.ANIMATION_FRAMES[idx % len(self.ANIMATION_FRAMES)])
                idx += 1
                time.sleep(self.ANIMATION_INTERVAL)
            except Exception:
                break

    def _handle_message(self, event: dict, say: Callable, client):
        text = self._extract_message_text(event)
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user_id = event.get("user")

        if not text:
            say("Please provide a message!", thread_ts=thread_ts)
            return

        log.info(f"[SLACK BOT] Channel: {channel}, Thread: {thread_ts}, User: {user_id}")

        chat_ctx = None
        if self._repository and user_id:
            chat_ctx = self._repository.get_or_create_chat(user_id, channel, thread_ts)

        result = say(self.ANIMATION_FRAMES[0], thread_ts=thread_ts)
        msg_ts = result.get("ts") if result else None

        stop_event = threading.Event()
        animation_thread = None
        if msg_ts:
            animation_thread = threading.Thread(
                target=self._animate_executing,
                args=(client, channel, msg_ts, stop_event),
                daemon=True
            )
            animation_thread.start()

        try:
            bot_response = self.process_message(text, chat_ctx)
        finally:
            stop_event.set()
            if animation_thread:
                animation_thread.join(timeout=1)

        if msg_ts:
            client.chat_update(channel=channel, ts=msg_ts, text=bot_response.reply)
        else:
            say(bot_response.reply, thread_ts=thread_ts)
        log.info(f"[SLACK BOT] ✅ Reply sent ({len(bot_response.reply)} chars)")

    def _handle_slash_command(self, respond: Callable, command: dict):
        text = command.get("text", "").strip()
        user_id = command.get("user_id", "unknown")
        user = command.get("user_name", "user")
        channel = command.get("channel_id", "unknown")

        if not text or text.lower() == "help":
            respond(self.get_help_text())
            return

        if text.lower() == "status":
            respond(self.get_status_text())
            return

        log.info(f"[SLACK BOT] Slash command from {user} in {channel}: {text[:50]}...")

        chat_ctx = None
        if self._repository and user_id:
            chat_ctx = self._repository.get_or_create_chat(user_id, channel)

        respond("⏳ Executing...")

        bot_response = self.process_message(text, chat_ctx)
        respond(f"✅ {bot_response.reply}" if bot_response.success else bot_response.reply)

    def get_help_text(self) -> str:
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

