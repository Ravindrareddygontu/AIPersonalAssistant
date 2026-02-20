import re
import logging
from typing import Optional, Any
from dataclasses import dataclass, field

from backend.config import BOT_MAX_MESSAGE_LENGTH_DEFAULT

log = logging.getLogger('bots.base')


@dataclass
class BaseBotConfig:
    bot_token: str = None
    workspace: str = None
    model: str = None

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)


@dataclass
class ChatContext:
    user_id: str
    chat_id: str
    platform: str
    channel_id: str = None
    thread_id: str = None
    auggie_session_id: str = None
    extra: dict = field(default_factory=dict)


@dataclass
class BotResponse:
    success: bool
    reply: str
    raw_content: str = None
    execution_time: float = 0.0
    session_id: str = None
    error: str = None


class BaseBot:

    MAX_MESSAGE_LENGTH: int = BOT_MAX_MESSAGE_LENGTH_DEFAULT
    PLATFORM: str = "unknown"
    ANIMATION_FRAMES: list = ["⏳ Executing.", "⏳ Executing..", "⏳ Executing..."]
    ANIMATION_INTERVAL: float = 0.2

    def __init__(self, config: BaseBotConfig = None, repository=None):
        self.config = config
        self._executor = None
        self._summarizer = None
        self._repository = repository
        self._running = False

    def _init_executor(self):
        if self._executor is None:
            from backend.services.auggie import AuggieExecutor, ResponseSummarizer
            self._executor = AuggieExecutor()
            self._summarizer = ResponseSummarizer

    def _ensure_initialized(self):
        raise NotImplementedError

    def _register_handlers(self):
        raise NotImplementedError

    def stop(self):
        self._running = False
        log.info(f"[{self.__class__.__name__}] Stopped")

    def extract_summary(self, content: str) -> tuple[str, Optional[str]]:
        pattern = r'(?:^|\n)-{2,3}SUMMARY-{2,3}\s*(.*?)\s*-{2,3}END_SUMMARY-{2,3}'
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            summary = matches[-1].strip()
            clean_content = re.sub(pattern, '', content, count=1, flags=re.DOTALL).strip()
            return clean_content, summary

        pattern_no_end = r'(?:^|\n)-{2,3}SUMMARY-{2,3}\s*'
        all_matches = list(re.finditer(pattern_no_end, content))
        if all_matches:
            last_match = all_matches[-1]
            summary = content[last_match.end():].strip()
            clean_content = content[:last_match.start()].strip()
            return clean_content, summary

        return content, None

    def truncate_message(self, content: str, max_length: int = None) -> str:
        max_len = max_length or self.MAX_MESSAGE_LENGTH
        if len(content) <= max_len:
            return content
        return content[:max_len - 50] + "\n\n... _(truncated)_"

    def summarize_if_needed(self, content: str, max_length: int = None) -> str:
        max_len = max_length or self.MAX_MESSAGE_LENGTH
        if len(content) <= max_len:
            return content
        if self._summarizer:
            return self._summarizer.summarize(content)
        return self.truncate_message(content, max_len)

    def format_response(self, content: str, execution_time: float, success: bool = True, error: str = None) -> BotResponse:
        if not success:
            return BotResponse(
                success=False,
                reply=f"❌ Error: {error}",
                raw_content=None,
                execution_time=execution_time,
                error=error
            )

        clean_content, summary = self.extract_summary(content)

        if summary:
            reply = f"{summary}\n\n⏱️ _{execution_time:.1f}s_"
        elif len(clean_content) > self.MAX_MESSAGE_LENGTH:
            truncated_summary = self._summarizer.summarize(clean_content) if self._summarizer else ""
            truncate_len = self.MAX_MESSAGE_LENGTH - 200
            reply = f"{clean_content[:truncate_len]}\n\n... _(truncated)_\n\n📝 *Summary:* {truncated_summary}\n\n⏱️ _{execution_time:.1f}s_"
        else:
            reply = f"{clean_content}\n\n⏱️ _{execution_time:.1f}s_"

        return BotResponse(
            success=True,
            reply=reply,
            raw_content=content,
            execution_time=execution_time
        )

    def process_message(self, text: str, chat_ctx: Any = None) -> BotResponse:
        log.info(f"[{self.PLATFORM.upper()} BOT] Processing: {text[:50]}...")

        session_id = None
        if chat_ctx and hasattr(chat_ctx, 'auggie_session_id'):
            session_id = chat_ctx.auggie_session_id

        try:
            self._init_executor()
            response = self._executor.execute(
                message=text,
                workspace=self.config.workspace,
                model=self.config.model,
                source='bot',
                session_id=session_id
            )

            bot_response = self.format_response(
                content=response.content or "",
                execution_time=response.execution_time,
                success=response.success,
                error=response.error
            )
            bot_response.session_id = response.session_id

            if chat_ctx and self._repository:
                self._repository.save_message(
                    chat_ctx.chat_id, text,
                    bot_response.raw_content or bot_response.reply,
                    response.execution_time
                )
                if response.session_id and hasattr(chat_ctx, 'auggie_session_id'):
                    if response.session_id != chat_ctx.auggie_session_id:
                        self._repository.save_auggie_session_id(chat_ctx.chat_id, response.session_id)

            return bot_response

        except Exception as e:
            log.exception(f"[{self.PLATFORM.upper()} BOT] Execution error: {e}")
            return BotResponse(
                success=False,
                reply=f"❌ Error: {str(e)}",
                error=str(e)
            )

    def get_help_text(self) -> str:
        return (
            "🤖 *Bot Help*\n\n"
            "*Commands:*\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/status - Check bot status\n\n"
            "*Usage:*\n"
            "Just send me any message and I'll process it!\n\n"
            "*Examples:*\n"
            "• `List all Python files`\n"
            "• `Explain this function`\n"
            "• `Fix the bug in main.py`"
        )

    def get_status_text(self) -> str:
        return f"🤖 Bot is running\n📁 Workspace: `{self.config.workspace or 'Not set'}`"

