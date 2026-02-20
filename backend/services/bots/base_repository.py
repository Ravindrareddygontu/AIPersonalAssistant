import logging
import uuid
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from backend.database import get_bot_chats_collection
from backend.services.base_repository import BaseRepository

log = logging.getLogger('bots.base_repository')

TITLE_MAX_LENGTH = 50
SESSION_TIMEOUT_MINUTES = 30


@dataclass
class BaseChatContext:
    chat_id: str
    user_id: str
    channel_id: str
    auggie_session_id: Optional[str] = None


class BaseBotChatRepository(BaseRepository):

    PLATFORM: str = "unknown"
    DEFAULT_TITLE: str = "Bot Chat"
    _indexes_created: bool = False

    def __init__(self):
        super().__init__()
        self._ensure_indexes()

    def _get_collection(self):
        return get_bot_chats_collection()

    def _ensure_indexes(self):
        cls = self.__class__
        if cls._indexes_created or self.collection is None:
            return
        try:
            self.collection.create_index('lookup_key', unique=True, background=True)
            self.collection.create_index('user_id', background=True)
            self.collection.create_index('platform', background=True)
            self.collection.create_index('id', background=True)
            cls._indexes_created = True
            log.info(f"[{self.PLATFORM.upper()}] Indexes created")
        except Exception as e:
            log.warning(f"[{self.PLATFORM.upper()}] Failed to create indexes: {e}")

    def _is_session_expired(self, chat: dict) -> bool:
        updated_at = chat.get('updated_at')
        if not updated_at:
            return True
        try:
            last_update = datetime.fromisoformat(updated_at)
            timeout_threshold = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            return last_update < timeout_threshold
        except (ValueError, TypeError):
            return True

    @abstractmethod
    def _make_lookup_key(self, *args, **kwargs) -> str:
        pass

    @abstractmethod
    def _create_context(self, chat: dict, session_expired: bool, **kwargs):
        pass

    @abstractmethod
    def _get_insert_fields(self, chat_id: str, lookup_key: str, now: str, **kwargs) -> dict:
        pass

    def _get_or_create_chat_internal(self, lookup_key: str, **context_kwargs):
        if self.collection is None:
            log.debug(f"[{self.PLATFORM.upper()}] MongoDB not available")
            return None

        try:
            chat_id = str(uuid.uuid4())[:8]
            now = datetime.utcnow().isoformat()

            existing_chat = self.collection.find_one({'lookup_key': lookup_key})
            session_expired = existing_chat and self._is_session_expired(existing_chat)

            if session_expired:
                log.info(f"[{self.PLATFORM.upper()}] Session expired for chat {existing_chat.get('id')}, resetting auggie_session_id")
                self.collection.update_one(
                    {'lookup_key': lookup_key},
                    {'$set': {'auggie_session_id': None, 'updated_at': now}}
                )

            insert_fields = self._get_insert_fields(chat_id, lookup_key, now, **context_kwargs)

            chat = self.collection.find_one_and_update(
                {'lookup_key': lookup_key},
                {
                    '$setOnInsert': insert_fields,
                    '$set': {'updated_at': now}
                },
                upsert=True,
                return_document=True
            )

            if chat.get('created_at') == now:
                log.info(f"[{self.PLATFORM.upper()}] Created chat: {chat['id']}")

            return self._create_context(chat, session_expired, **context_kwargs)

        except Exception as e:
            log.error(f"[{self.PLATFORM.upper()}] Failed to get/create chat: {e}")
            return None

    def save_message(self, chat_id: str, question: str, answer: str, execution_time: Optional[float] = None) -> bool:
        if self.collection is None or not chat_id:
            return False

        try:
            now = datetime.utcnow().isoformat()
            msg_id = f"{chat_id}-{uuid.uuid4().hex[:8]}"

            message = {
                'id': msg_id,
                'question': question,
                'answer': answer,
                'question_time': now,
                'answer_time': now,
                'execution_time': execution_time
            }

            result = self.collection.update_one(
                {'id': chat_id},
                {
                    '$push': {'messages': message},
                    '$set': {'updated_at': now}
                }
            )

            if result.matched_count == 0:
                log.warning(f"[{self.PLATFORM.upper()}] Chat {chat_id} not found")
                return False

            self.collection.update_one(
                {'id': chat_id, 'title': self.DEFAULT_TITLE},
                {'$set': {'title': self.generate_title(question, TITLE_MAX_LENGTH)}}
            )

            log.info(f"[{self.PLATFORM.upper()}] Saved message to chat {chat_id}")
            return True

        except Exception as e:
            log.error(f"[{self.PLATFORM.upper()}] Failed to save message: {e}")
            return False

    def save_auggie_session_id(self, chat_id: str, session_id: str) -> bool:
        if self.collection is None or not chat_id or not session_id:
            return False
        try:
            self.collection.update_one(
                {'id': chat_id},
                {'$set': {'auggie_session_id': session_id, 'updated_at': datetime.utcnow().isoformat()}}
            )
            log.info(f"[{self.PLATFORM.upper()}] Saved auggie_session_id={session_id} for chat {chat_id}")
            return True
        except Exception as e:
            log.error(f"[{self.PLATFORM.upper()}] Failed to save auggie_session_id: {e}")
            return False

    def get_auggie_session_id(self, chat_id: str) -> Optional[str]:
        if self.collection is None or not chat_id:
            return None
        chat = self.collection.find_one({'id': chat_id})
        return chat.get('auggie_session_id') if chat else None

