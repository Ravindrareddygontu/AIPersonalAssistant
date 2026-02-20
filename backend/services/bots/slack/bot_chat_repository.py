from typing import Optional
from dataclasses import dataclass

from backend.services.bots.base_repository import BaseBotChatRepository


@dataclass
class BotChatContext:
    chat_id: str
    user_id: str
    channel_id: str
    thread_ts: Optional[str] = None
    auggie_session_id: Optional[str] = None


class BotChatRepository(BaseBotChatRepository):

    PLATFORM = "slack"
    DEFAULT_TITLE = "Slack Chat"

    def _make_lookup_key(self, user_id: str, channel_id: str, thread_ts: Optional[str] = None) -> str:
        if thread_ts:
            return f"{self.PLATFORM}:{user_id}:{channel_id}:{thread_ts}"
        return f"{self.PLATFORM}:{user_id}:{channel_id}"

    def _get_insert_fields(self, chat_id: str, lookup_key: str, now: str, **kwargs) -> dict:
        return {
            'id': chat_id,
            'lookup_key': lookup_key,
            'platform': self.PLATFORM,
            'user_id': kwargs.get('user_id'),
            'channel_id': kwargs.get('channel_id'),
            'thread_ts': kwargs.get('thread_ts'),
            'title': self.DEFAULT_TITLE,
            'created_at': now,
            'messages': [],
            'auggie_session_id': None
        }

    def _create_context(self, chat: dict, session_expired: bool, **kwargs):
        auggie_session_id = None if session_expired else chat.get('auggie_session_id')
        return BotChatContext(
            chat_id=chat['id'],
            user_id=kwargs.get('user_id'),
            channel_id=kwargs.get('channel_id'),
            thread_ts=kwargs.get('thread_ts'),
            auggie_session_id=auggie_session_id
        )

    def get_or_create_chat(self, user_id: str, channel_id: str, thread_ts: Optional[str] = None) -> Optional[BotChatContext]:
        lookup_key = self._make_lookup_key(user_id, channel_id, thread_ts)
        return self._get_or_create_chat_internal(
            lookup_key,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts
        )

