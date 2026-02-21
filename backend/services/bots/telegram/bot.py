import os
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass

from backend.services.bots.base import BaseBot, BaseBotConfig
from backend.config import DEFAULT_WORKSPACE_PATH, BOT_MAX_MESSAGE_LENGTH_TELEGRAM

log = logging.getLogger('telegram.bot')

CONNECT_TIMEOUT = 20.0
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0
POOL_TIMEOUT = 10.0


@dataclass
class TelegramBotConfig(BaseBotConfig):

    def __post_init__(self):
        self.bot_token = self.bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.workspace = self.workspace or os.environ.get('TELEGRAM_WORKSPACE', DEFAULT_WORKSPACE_PATH)
        self.model = self.model or os.environ.get('TELEGRAM_MODEL')


class TelegramBot(BaseBot):

    MAX_MESSAGE_LENGTH = BOT_MAX_MESSAGE_LENGTH_TELEGRAM
    PLATFORM = "telegram"

    def __init__(self, config: TelegramBotConfig = None, repository=None):
        super().__init__(config or TelegramBotConfig(), repository)
        self._application = None

    def _ensure_initialized(self):
        if self._application is not None:
            return

        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
            from telegram.request import HTTPXRequest
        except ImportError:
            raise ImportError("Run: pip install python-telegram-bot")

        request = HTTPXRequest(
            connect_timeout=CONNECT_TIMEOUT,
            read_timeout=READ_TIMEOUT,
            write_timeout=WRITE_TIMEOUT,
            pool_timeout=POOL_TIMEOUT,
        )

        self._application = (
            Application.builder()
            .token(self.config.bot_token)
            .request(request)
            .build()
        )
        self._init_executor()

        if self._repository is None:
            from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository
            self._repository = TelegramChatRepository()

        self._register_handlers()
        self._register_error_handler()
        log.info("[TELEGRAM BOT] Initialized")

    def _register_handlers(self):
        from telegram.ext import CommandHandler, MessageHandler, filters

        self._application.add_handler(CommandHandler("start", self._handle_start))
        self._application.add_handler(CommandHandler("help", self._handle_help))
        self._application.add_handler(CommandHandler("status", self._handle_status))
        self._application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        log.info("[TELEGRAM BOT] Handlers registered")

    def _register_error_handler(self):
        async def error_handler(update, context):
            from telegram.error import TimedOut, NetworkError, Conflict

            error = context.error
            if isinstance(error, TimedOut):
                log.warning(f"[TELEGRAM BOT] Request timed out: {error}")
            elif isinstance(error, Conflict):
                log.error(f"[TELEGRAM BOT] Conflict - another instance running: {error}")
            elif isinstance(error, NetworkError):
                log.warning(f"[TELEGRAM BOT] Network error: {error}")
            else:
                log.error(f"[TELEGRAM BOT] Unhandled error: {error}", exc_info=context.error)

        self._application.add_error_handler(error_handler)
        log.info("[TELEGRAM BOT] Error handler registered")

    async def _handle_start(self, update, _context):
        await update.message.reply_text(
            "👋 Hi! I'm Auggie Bot.\n\n"
            "Send me any coding question or task, and I'll help you out!\n\n"
            "Commands:\n"
            "/help - Show this help\n"
            "/status - Check bot status"
        )

    async def _handle_help(self, update, _context):
        await update.message.reply_text(self.get_help_text(), parse_mode='Markdown')

    async def _handle_status(self, update, _context):
        status = self.get_status_text() + f"\n🔧 Model: {self.config.model or 'default'}"
        await update.message.reply_text(status, parse_mode='Markdown')

    async def _animate_executing(self, message, stop_event: asyncio.Event):
        idx = 1
        await asyncio.sleep(self.ANIMATION_INTERVAL)
        while not stop_event.is_set():
            try:
                await message.edit_text(self.ANIMATION_FRAMES[idx % len(self.ANIMATION_FRAMES)])
                idx += 1
                await asyncio.sleep(self.ANIMATION_INTERVAL)
            except Exception:
                break

    async def _handle_message(self, update, _context):
        text = update.message.text.strip()
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)

        if not text:
            await update.message.reply_text("Please provide a message!")
            return

        chat_ctx = None
        if self._repository and user_id:
            chat_ctx = self._repository.get_or_create_chat(user_id, str(chat_id))

        thinking_msg = await update.message.reply_text(self.ANIMATION_FRAMES[0])

        stop_event = asyncio.Event()
        animation_task = asyncio.create_task(self._animate_executing(thinking_msg, stop_event))

        try:
            bot_response = await asyncio.to_thread(self.process_message, text, chat_ctx)
        finally:
            stop_event.set()
            animation_task.cancel()
            try:
                await animation_task
            except asyncio.CancelledError:
                pass

        await thinking_msg.edit_text(bot_response.reply, parse_mode='Markdown')

    @property
    def application(self):
        self._ensure_initialized()
        return self._application

    def run_polling(self):
        if not self.config.is_configured:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        self._ensure_initialized()
        log.info("[TELEGRAM BOT] Starting polling...")
        self._running = True
        self._application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message"],
        )

    def stop(self):
        self._running = False
        if self._application:
            self._application.stop()
        log.info("[TELEGRAM BOT] Stopped")


def create_telegram_bot(
    bot_token: str = None,
    workspace: str = None,
    model: str = None
) -> TelegramBot:
    config = TelegramBotConfig(
        bot_token=bot_token,
        workspace=workspace,
        model=model
    )
    return TelegramBot(config)

