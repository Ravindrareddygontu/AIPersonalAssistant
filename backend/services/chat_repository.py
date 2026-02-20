import logging
from datetime import datetime
from backend.database import get_chats_collection, is_db_available_cached
from backend.services import message_service as msg_svc

log = logging.getLogger('chat.repository')


class ChatRepository:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self._collection = None
        self._db_available = None

        # Check DB availability upfront using cached status (non-blocking)
        if not is_db_available_cached():
            self._db_available = False
            log.debug(f"ChatRepository for {chat_id}: DB not available (cached)")

    @property
    def collection(self):
        # If we already know DB is unavailable, don't try again
        if self._db_available is False:
            return None
        if self._collection is None:
            self._collection = get_chats_collection()
            self._db_available = self._collection is not None
        return self._collection

    @property
    def is_db_available(self) -> bool:
        if self._db_available is None:
            # Use cached check first
            if not is_db_available_cached():
                self._db_available = False
                return False
            # Trigger collection load to check availability
            _ = self.collection
        return self._db_available

    def get_chat(self) -> dict | None:
        if not self.chat_id:
            return None
        if self.collection is None:
            log.warning(f"MongoDB not available, cannot get chat {self.chat_id}")
            return None
        return self.collection.find_one({'id': self.chat_id})

    def save_question(self, question_content: str) -> str | None:
        if not self.chat_id:
            return None

        try:
            chat = self.get_chat()
            if not chat:
                log.warning(f"Chat {self.chat_id} not found, cannot save question")
                return None

            messages = chat.get('messages', [])
            messages, msg_id = msg_svc.add_question(self.chat_id, messages, question_content)

            # Update title if it's still "New Chat"
            title = chat.get('title', 'New Chat')
            if title == 'New Chat':
                title = self._generate_title(question_content)

            self._update_chat(messages, title)
            log.info(f"Saved question to chat {self.chat_id}, message_id: {msg_id}")
            return msg_id

        except Exception as e:
            log.error(f"Failed to save question: {e}")
            return None

    def save_answer(self, message_id: str, cleaned_content: str) -> bool:
        if not self.chat_id or not message_id:
            return False

        try:
            chat = self.get_chat()
            if not chat:
                log.warning(f"Chat {self.chat_id} not found, cannot save answer")
                return False

            messages = chat.get('messages', [])
            messages = msg_svc.add_answer(messages, message_id, cleaned_content)

            self._update_chat(messages)
            log.info(f"Saved answer to chat {self.chat_id}, message_id: {message_id}")
            return True

        except Exception as e:
            log.error(f"Failed to save answer: {e}")
            return False

    def _update_chat(self, messages: list, title: str = None, streaming_status: str = None) -> None:
        if self.collection is None:
            log.warning(f"MongoDB not available, skipping chat update for {self.chat_id}")
            return

        update_data = {
            'messages': messages,
            'updated_at': datetime.utcnow().isoformat()
        }
        if title:
            update_data['title'] = title
        if streaming_status is not None:
            update_data['streaming_status'] = streaming_status

        self.collection.update_one(
            {'id': self.chat_id},
            {'$set': update_data}
        )

    def set_streaming_status(self, status: str) -> None:
        if not self.chat_id:
            return
        if self.collection is None:
            log.warning(f"MongoDB not available, skipping streaming status update for {self.chat_id}")
            return
        self.collection.update_one(
            {'id': self.chat_id},
            {'$set': {'streaming_status': status, 'updated_at': datetime.utcnow().isoformat()}}
        )
        log.info(f"Set streaming_status={status} for chat {self.chat_id}")

    def get_auggie_session_id(self) -> str | None:
        chat = self.get_chat()
        if chat:
            return chat.get('auggie_session_id')
        return None

    def save_auggie_session_id(self, session_id: str) -> bool:
        if not self.chat_id or not session_id:
            return False
        if self.collection is None:
            log.warning(f"MongoDB not available, cannot save auggie_session_id for {self.chat_id}")
            return False
        try:
            self.collection.update_one(
                {'id': self.chat_id},
                {'$set': {'auggie_session_id': session_id, 'updated_at': datetime.utcnow().isoformat()}}
            )
            log.info(f"Saved auggie_session_id={session_id} for chat {self.chat_id}")
            return True
        except Exception as e:
            log.error(f"Failed to save auggie_session_id: {e}")
            return False

    def save_partial_answer(self, message_id: str, partial_content: str) -> bool:
        if not self.chat_id or not message_id:
            return False
        try:
            chat = self.get_chat()
            if not chat:
                return False
            messages = chat.get('messages', [])
            # Update the answer in the message pair
            for msg in messages:
                if msg.get('id') == message_id:
                    msg['answer'] = partial_content
                    msg['partial'] = True  # Mark as incomplete
                    break
            self._update_chat(messages, streaming_status='streaming')
            return True
        except Exception as e:
            log.error(f"Failed to save partial answer: {e}")
            return False

    @staticmethod
    def _generate_title(question: str, max_length: int = 50) -> str:
        if len(question) > max_length:
            return question[:max_length] + '...'
        return question

