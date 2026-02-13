"""
ChatRepository - Handles all database operations for chat messages.

Follows Single Responsibility Principle: Only handles DB persistence.
"""

import logging
from datetime import datetime
from backend.database import get_chats_collection
from backend.services import message_service as msg_svc

log = logging.getLogger('chat.repository')


class ChatRepository:
    """Repository for chat message persistence operations."""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self._collection = None

    @property
    def collection(self):
        """Lazy-load the MongoDB collection."""
        if self._collection is None:
            self._collection = get_chats_collection()
        return self._collection

    def get_chat(self) -> dict | None:
        """Retrieve a chat by ID."""
        if not self.chat_id:
            return None
        return self.collection.find_one({'id': self.chat_id})

    def save_question(self, question_content: str) -> str | None:
        """
        Save a new question to the chat and return the message ID.
        
        Args:
            question_content: The user's question text
            
        Returns:
            The generated message ID, or None if save failed
        """
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

    def save_answer(self, message_id: str, cleaned_content: str, raw_content: str = None) -> bool:
        """
        Save an answer to an existing question.
        
        Args:
            message_id: The ID of the Q&A pair to update
            cleaned_content: Cleaned response for display
            raw_content: Original raw response (optional)
            
        Returns:
            True if save succeeded, False otherwise
        """
        if not self.chat_id or not message_id:
            return False

        try:
            chat = self.get_chat()
            if not chat:
                log.warning(f"Chat {self.chat_id} not found, cannot save answer")
                return False

            messages = chat.get('messages', [])
            messages = msg_svc.add_answer(messages, message_id, cleaned_content, raw_answer=raw_content)

            self._update_chat(messages)
            log.info(f"Saved answer to chat {self.chat_id}, message_id: {message_id}")
            return True

        except Exception as e:
            log.error(f"Failed to save answer: {e}")
            return False

    def _update_chat(self, messages: list, title: str = None) -> None:
        """Update chat document in database."""
        update_data = {
            'messages': messages,
            'updated_at': datetime.utcnow().isoformat()
        }
        if title:
            update_data['title'] = title

        self.collection.update_one(
            {'id': self.chat_id},
            {'$set': update_data}
        )

    @staticmethod
    def _generate_title(question: str, max_length: int = 50) -> str:
        """Generate a chat title from the first question."""
        if len(question) > max_length:
            return question[:max_length] + '...'
        return question

