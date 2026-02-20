"""
Tests for chat_repository.py - ChatRepository class with mocked database.

Tests cover:
- ChatRepository initialization
- get_chat: Retrieving chats by ID
- save_question: Saving new questions
- save_answer: Saving answers to existing questions
- _update_chat: Updating chat documents
- set_streaming_status: Setting streaming status
- save_partial_answer: Saving partial streaming content
- _generate_title: Generating titles from questions
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestChatRepositoryInit:
    """Test ChatRepository initialization."""

    def test_init_with_chat_id(self):
        """Test initialization with chat ID."""
        from backend.services.chat_repository import ChatRepository
        
        repo = ChatRepository("test-chat-123")
        assert repo.chat_id == "test-chat-123"
        assert repo._collection is None  # Lazy loaded


class TestGetChat:
    """Test get_chat method."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_get_chat_found(self, mock_collection_fn):
        """Test getting existing chat."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {'id': 'chat-1', 'title': 'Test Chat'}
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        result = repo.get_chat()
        
        assert result is not None
        assert result['id'] == 'chat-1'
        mock_col.find_one.assert_called_with({'id': 'chat-1'})

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_get_chat_not_found(self, mock_collection_fn):
        """Test getting non-existent chat."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("nonexistent")
        result = repo.get_chat()
        
        assert result is None

    def test_get_chat_no_id(self):
        """Test get_chat with no chat ID."""
        from backend.services.chat_repository import ChatRepository
        
        repo = ChatRepository("")
        result = repo.get_chat()
        
        assert result is None


class TestSaveQuestion:
    """Test save_question method."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_question_success(self, mock_collection_fn):
        """Test successful question save."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            'id': 'chat-1',
            'title': 'New Chat',
            'messages': []
        }
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        msg_id = repo.save_question("What is Python?")
        
        assert msg_id is not None
        assert msg_id.startswith("chat-1-")
        mock_col.update_one.assert_called_once()

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_question_updates_title(self, mock_collection_fn):
        """Test that first question updates chat title."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            'id': 'chat-1',
            'title': 'New Chat',
            'messages': []
        }
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        repo.save_question("What is Python?")
        
        # Check that title was updated
        call_args = mock_col.update_one.call_args
        update_data = call_args[0][1]['$set']
        assert 'title' in update_data
        assert update_data['title'] == "What is Python?"

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_question_no_chat(self, mock_collection_fn):
        """Test save_question when chat doesn't exist."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("nonexistent")
        msg_id = repo.save_question("Question")
        
        assert msg_id is None


class TestSaveAnswer:
    """Test save_answer method."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_answer_success(self, mock_collection_fn):
        """Test successful answer save."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            'id': 'chat-1',
            'messages': [{'id': 'msg-1', 'question': 'Q', 'answer': None}]
        }
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        result = repo.save_answer("msg-1", "The answer is 42.")
        
        assert result == True
        mock_col.update_one.assert_called_once()

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_answer_no_chat(self, mock_collection_fn):
        """Test save_answer when chat doesn't exist."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("nonexistent")
        result = repo.save_answer("msg-1", "Answer")
        
        assert result == False

    def test_save_answer_no_message_id(self):
        """Test save_answer with no message ID."""
        from backend.services.chat_repository import ChatRepository
        
        repo = ChatRepository("chat-1")
        result = repo.save_answer("", "Answer")
        
        assert result == False


class TestSetStreamingStatus:
    """Test set_streaming_status method."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_set_streaming_status(self, mock_collection_fn):
        """Test setting streaming status."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        repo.set_streaming_status("streaming")
        
        call_args = mock_col.update_one.call_args
        update_data = call_args[0][1]['$set']
        assert update_data['streaming_status'] == "streaming"


class TestSavePartialAnswer:
    """Test save_partial_answer method."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_partial_answer(self, mock_collection_fn):
        """Test saving partial streaming content."""
        from backend.services.chat_repository import ChatRepository
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            'id': 'chat-1',
            'messages': [{'id': 'msg-1', 'question': 'Q', 'answer': None}]
        }
        mock_collection_fn.return_value = mock_col
        
        repo = ChatRepository("chat-1")
        result = repo.save_partial_answer("msg-1", "Partial content...")
        
        assert result == True


class TestGenerateTitle:
    """Test _generate_title static method."""

    def test_short_question(self):
        """Test title generation for short question."""
        from backend.services.chat_repository import ChatRepository

        result = ChatRepository._generate_title("What is Python?")
        assert result == "What is Python?"

    def test_long_question_truncated(self):
        """Test that long questions are truncated."""
        from backend.services.chat_repository import ChatRepository

        long_q = "A" * 100
        result = ChatRepository._generate_title(long_q)

        assert len(result) == 53  # 50 + "..."
        assert result.endswith("...")

    def test_custom_max_length(self):
        """Test custom max length."""
        from backend.services.chat_repository import ChatRepository

        result = ChatRepository._generate_title("A" * 50, max_length=20)
        assert len(result) == 23  # 20 + "..."


class TestAuggieSessionId:
    """Test auggie_session_id methods for session persistence."""

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_get_auggie_session_id_exists(self, mock_collection_fn):
        """Test getting existing auggie_session_id."""
        from backend.services.chat_repository import ChatRepository

        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            'id': 'chat-1',
            'auggie_session_id': 'session-abc-123'
        }
        mock_collection_fn.return_value = mock_col

        repo = ChatRepository("chat-1")
        result = repo.get_auggie_session_id()

        assert result == 'session-abc-123'

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_get_auggie_session_id_none(self, mock_collection_fn):
        """Test getting auggie_session_id when not set."""
        from backend.services.chat_repository import ChatRepository

        mock_col = MagicMock()
        mock_col.find_one.return_value = {'id': 'chat-1'}
        mock_collection_fn.return_value = mock_col

        repo = ChatRepository("chat-1")
        result = repo.get_auggie_session_id()

        assert result is None

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_get_auggie_session_id_no_chat(self, mock_collection_fn):
        """Test getting auggie_session_id when chat doesn't exist."""
        from backend.services.chat_repository import ChatRepository

        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection_fn.return_value = mock_col

        repo = ChatRepository("nonexistent")
        result = repo.get_auggie_session_id()

        assert result is None

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_auggie_session_id_success(self, mock_collection_fn):
        """Test saving auggie_session_id successfully."""
        from backend.services.chat_repository import ChatRepository

        mock_col = MagicMock()
        mock_collection_fn.return_value = mock_col

        repo = ChatRepository("chat-1")
        result = repo.save_auggie_session_id("session-xyz-789")

        assert result is True
        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        update_data = call_args[0][1]['$set']
        assert update_data['auggie_session_id'] == 'session-xyz-789'
        assert 'updated_at' in update_data

    def test_save_auggie_session_id_no_chat_id(self):
        """Test save_auggie_session_id with no chat ID."""
        from backend.services.chat_repository import ChatRepository

        repo = ChatRepository("")
        result = repo.save_auggie_session_id("session-123")

        assert result is False

    def test_save_auggie_session_id_no_session_id(self):
        """Test save_auggie_session_id with no session ID."""
        from backend.services.chat_repository import ChatRepository

        repo = ChatRepository("chat-1")
        result = repo.save_auggie_session_id("")

        assert result is False

    @patch('backend.services.chat_repository.get_chats_collection')
    def test_save_auggie_session_id_db_error(self, mock_collection_fn):
        """Test save_auggie_session_id handles DB errors."""
        from backend.services.chat_repository import ChatRepository

        mock_col = MagicMock()
        mock_col.update_one.side_effect = Exception("DB connection lost")
        mock_collection_fn.return_value = mock_col

        repo = ChatRepository("chat-1")
        result = repo.save_auggie_session_id("session-123")

        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

