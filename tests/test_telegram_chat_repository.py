import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTelegramChatRepositoryInit:

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_init_db_available(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_collection_fn.return_value = mock_col
        repo = TelegramChatRepository()
        assert repo._db_available is None or repo._db_available is True

    @patch('backend.services.base_repository.is_db_available_cached')
    def test_init_db_not_available(self, mock_cached):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = False
        repo = TelegramChatRepository()
        assert repo._db_available is False


class TestMakeLookupKey:

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_lookup_key_format(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = True
        mock_collection_fn.return_value = MagicMock()
        repo = TelegramChatRepository()
        key = repo._make_lookup_key("123456", "789012")
        assert key == "telegram:123456:789012"


class TestGetOrCreateChat:

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_existing_chat(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository
        from datetime import datetime

        mock_cached.return_value = True
        mock_col = MagicMock()
        recent_time = datetime.utcnow().isoformat()
        existing_chat = {
            'id': 'abc123',
            'lookup_key': '123456:789012',
            'user_id': '123456',
            'telegram_chat_id': '789012',
            'auggie_session_id': 'session-xyz',
            'created_at': '2025-01-01T00:00:00',
            'updated_at': recent_time
        }
        mock_col.find_one.return_value = existing_chat
        mock_col.find_one_and_update.return_value = existing_chat
        mock_collection_fn.return_value = mock_col

        repo = TelegramChatRepository()
        ctx = repo.get_or_create_chat("123456", "789012")

        assert ctx is not None
        assert ctx.chat_id == 'abc123'
        assert ctx.user_id == '123456'
        assert ctx.telegram_chat_id == '789012'
        assert ctx.auggie_session_id == 'session-xyz'
        mock_col.find_one_and_update.assert_called_once()

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_create_new_chat(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository
        from datetime import datetime

        mock_cached.return_value = True
        mock_col = MagicMock()
        now = datetime.utcnow().isoformat()
        mock_col.find_one_and_update.return_value = {
            'id': 'new-chat',
            'lookup_key': '123456:789012',
            'user_id': '123456',
            'telegram_chat_id': '789012',
            'created_at': now
        }
        mock_collection_fn.return_value = mock_col

        repo = TelegramChatRepository()
        ctx = repo.get_or_create_chat("123456", "789012")

        assert ctx is not None
        assert ctx.user_id == '123456'
        mock_col.find_one_and_update.assert_called_once()
        call_kwargs = mock_col.find_one_and_update.call_args[1]
        assert call_kwargs['upsert'] is True

    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_or_create_db_unavailable(self, mock_cached):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = False
        repo = TelegramChatRepository()
        ctx = repo.get_or_create_chat("123456", "789012")

        assert ctx is None


class TestSaveMessage:

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_success(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_col.update_one.return_value = mock_result
        mock_collection_fn.return_value = mock_col

        repo = TelegramChatRepository()
        result = repo.save_message("abc123", "What is Python?", "Python is a language.", 5.2)

        assert result is True
        assert mock_col.update_one.call_count == 2
        first_call_args = mock_col.update_one.call_args_list[0][0][1]
        assert '$push' in first_call_args
        assert first_call_args['$push']['messages']['question'] == "What is Python?"

    @patch('backend.services.bots.base_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_chat_not_found(self, mock_cached, mock_collection_fn):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_col.update_one.return_value = mock_result
        mock_collection_fn.return_value = mock_col

        repo = TelegramChatRepository()
        result = repo.save_message("nonexistent", "Question", "Answer", 1.0)

        assert result is False


class TestTelegramChatContext:

    def test_dataclass_creation(self):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatContext

        ctx = TelegramChatContext(
            chat_id="abc123",
            user_id="123456",
            telegram_chat_id="789012",
            auggie_session_id="session-xyz"
        )

        assert ctx.chat_id == "abc123"
        assert ctx.user_id == "123456"
        assert ctx.telegram_chat_id == "789012"
        assert ctx.auggie_session_id == "session-xyz"

    def test_dataclass_defaults(self):
        from backend.services.bots.telegram.bot_chat_repository import TelegramChatContext

        ctx = TelegramChatContext(chat_id="abc123", user_id="123456", telegram_chat_id="789012")

        assert ctx.auggie_session_id is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

