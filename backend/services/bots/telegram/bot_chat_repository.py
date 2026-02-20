from typing import Optional
from dataclasses import dataclass

from backend.services.bots.base_repository import BaseBotChatRepository


@dataclass
class TelegramChatContext:
    chat_id: str
    user_id: str
    telegram_chat_id: str
    auggie_session_id: Optional[str] = None


class TelegramChatRepository(BaseBotChatRepository):

    PLATFORM = "telegram"
    DEFAULT_TITLE = "Telegram Chat"

    def _make_lookup_key(self, user_id: str, telegram_chat_id: str) -> str:
        return f"{self.PLATFORM}:{user_id}:{telegram_chat_id}"

    def _get_insert_fields(self, chat_id: str, lookup_key: str, now: str, **kwargs) -> dict:
        telegram_chat_id = kwargs.get('telegram_chat_id')
        return {
            'id': chat_id,
            'lookup_key': lookup_key,
            'platform': self.PLATFORM,
            'user_id': kwargs.get('user_id'),
            'channel_id': telegram_chat_id,
            'telegram_chat_id': telegram_chat_id,
            'title': self.DEFAULT_TITLE,
            'created_at': now,
            'messages': [],
            'auggie_session_id': None
        }

    def _create_context(self, chat: dict, session_expired: bool, **kwargs):
        auggie_session_id = None if session_expired else chat.get('auggie_session_id')
        return TelegramChatContext(
            chat_id=chat['id'],
            user_id=kwargs.get('user_id'),
            telegram_chat_id=kwargs.get('telegram_chat_id'),
            auggie_session_id=auggie_session_id
        )

    def get_or_create_chat(self, user_id: str, telegram_chat_id: str) -> Optional[TelegramChatContext]:
        lookup_key = self._make_lookup_key(user_id, telegram_chat_id)
        return self._get_or_create_chat_internal(
            lookup_key,
            user_id=user_id,
            telegram_chat_id=telegram_chat_id
        )

