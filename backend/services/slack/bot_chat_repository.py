import logging
import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from backend.database import get_bot_chats_collection
from backend.services.base_repository import BaseRepository

log = logging.getLogger('slack.bot_chat_repository')

TITLE_MAX_LENGTH = 50
DEFAULT_TITLE = 'Slack Chat'


@dataclass
class BotChatContext:
    chat_id: str
    user_id: str
    channel_id: str
    thread_ts: Optional[str] = None
    auggie_session_id: Optional[str] = None


class BotChatRepository(BaseRepository):

    _indexes_created = False

    def __init__(self):
        super().__init__()
        self._ensure_indexes()

    def _get_collection(self):
        return get_bot_chats_collection()

    def _ensure_indexes(self):
        if BotChatRepository._indexes_created or self.collection is None:
            return
        try:
            self.collection.create_index('lookup_key', unique=True, background=True)
            self.collection.create_index('user_id', background=True)
            BotChatRepository._indexes_created = True
            log.info("[BOT_CHAT] Indexes created")
        except Exception as e:
            log.warning(f"[BOT_CHAT] Failed to create indexes: {e}")

    def get_or_create_chat(self, user_id: str, channel_id: str, thread_ts: Optional[str] = None) -> Optional[BotChatContext]:
        if self.collection is None:
            log.debug("MongoDB not available, cannot get/create bot chat")
            return None

        lookup_key = self._make_lookup_key(user_id, channel_id, thread_ts)

        try:
            chat_id = str(uuid.uuid4())[:8]
            now = datetime.utcnow().isoformat()

            chat = self.collection.find_one_and_update(
                {'lookup_key': lookup_key},
                {
                    '$setOnInsert': {
                        'id': chat_id,
                        'lookup_key': lookup_key,
                        'user_id': user_id,
                        'channel_id': channel_id,
                        'thread_ts': thread_ts,
                        'title': DEFAULT_TITLE,
                        'created_at': now,
                        'messages': [],
                        'auggie_session_id': None
                    },
                    '$set': {'updated_at': now}
                },
                upsert=True,
                return_document=True
            )

            if chat.get('created_at') == now:
                log.info(f"[BOT_CHAT] Created chat: {chat['id']} for user={user_id}")

            return BotChatContext(
                chat_id=chat['id'],
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                auggie_session_id=chat.get('auggie_session_id')
            )

        except Exception as e:
            log.error(f"[BOT_CHAT] Failed to get/create chat: {e}")
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
                log.warning(f"[BOT_CHAT] Chat {chat_id} not found")
                return False

            self.collection.update_one(
                {'id': chat_id, 'title': DEFAULT_TITLE},
                {'$set': {'title': self.generate_title(question, TITLE_MAX_LENGTH)}}
            )

            log.info(f"[BOT_CHAT] Saved message to chat {chat_id}")
            return True

        except Exception as e:
            log.error(f"[BOT_CHAT] Failed to save message: {e}")
            return False

    def save_auggie_session_id(self, chat_id: str, session_id: str) -> bool:
        if self.collection is None or not chat_id or not session_id:
            return False
        try:
            self.collection.update_one(
                {'id': chat_id},
                {'$set': {'auggie_session_id': session_id, 'updated_at': datetime.utcnow().isoformat()}}
            )
            log.info(f"[BOT_CHAT] Saved auggie_session_id={session_id} for chat {chat_id}")
            return True
        except Exception as e:
            log.error(f"[BOT_CHAT] Failed to save auggie_session_id: {e}")
            return False

    def get_auggie_session_id(self, chat_id: str) -> Optional[str]:
        if self.collection is None or not chat_id:
            return None
        chat = self.collection.find_one({'id': chat_id})
        return chat.get('auggie_session_id') if chat else None

    @staticmethod
    def _make_lookup_key(user_id: str, channel_id: str, thread_ts: Optional[str] = None) -> str:
        if thread_ts:
            return f"{user_id}:{channel_id}:{thread_ts}"
        return f"{user_id}:{channel_id}"

