import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBotChatRepositoryInit:

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_init_db_available(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_collection_fn.return_value = mock_col
        repo = BotChatRepository()
        assert repo._db_available is None or repo._db_available is True

    @patch('backend.services.base_repository.is_db_available_cached')
    def test_init_db_not_available(self, mock_cached):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = False
        repo = BotChatRepository()
        assert repo._db_available is False


class TestMakeLookupKey:

    def test_lookup_key_without_thread(self):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        key = BotChatRepository._make_lookup_key("U123", "C456")
        assert key == "U123:C456"

    def test_lookup_key_with_thread(self):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        key = BotChatRepository._make_lookup_key("U123", "C456", "1234567890.123")
        assert key == "U123:C456:1234567890.123"


class TestGetOrCreateChat:

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_existing_chat(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_col.find_one_and_update.return_value = {
            'id': 'abc123',
            'lookup_key': 'U123:C456',
            'user_id': 'U123',
            'channel_id': 'C456',
            'auggie_session_id': 'session-xyz',
            'created_at': '2025-01-01T00:00:00'
        }
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        ctx = repo.get_or_create_chat("U123", "C456")

        assert ctx is not None
        assert ctx.chat_id == 'abc123'
        assert ctx.user_id == 'U123'
        assert ctx.channel_id == 'C456'
        assert ctx.auggie_session_id == 'session-xyz'
        mock_col.find_one_and_update.assert_called_once()

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_create_new_chat(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository
        from datetime import datetime

        mock_cached.return_value = True
        mock_col = MagicMock()
        now = datetime.utcnow().isoformat()
        mock_col.find_one_and_update.return_value = {
            'id': 'new-chat',
            'lookup_key': 'U123:C456:1234567890.123',
            'user_id': 'U123',
            'channel_id': 'C456',
            'thread_ts': '1234567890.123',
            'created_at': now
        }
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        ctx = repo.get_or_create_chat("U123", "C456", "1234567890.123")

        assert ctx is not None
        assert ctx.user_id == 'U123'
        assert ctx.channel_id == 'C456'
        assert ctx.thread_ts == '1234567890.123'
        mock_col.find_one_and_update.assert_called_once()
        call_kwargs = mock_col.find_one_and_update.call_args[1]
        assert call_kwargs['upsert'] is True

    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_or_create_db_unavailable(self, mock_cached):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = False
        repo = BotChatRepository()
        ctx = repo.get_or_create_chat("U123", "C456")

        assert ctx is None


class TestSaveMessage:

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_success(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_col.update_one.return_value = mock_result
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        result = repo.save_message("abc123", "What is Python?", "Python is a language.", 5.2)

        assert result is True
        assert mock_col.update_one.call_count == 2
        first_call_args = mock_col.update_one.call_args_list[0][0][1]
        assert '$push' in first_call_args
        assert first_call_args['$push']['messages']['question'] == "What is Python?"
        assert first_call_args['$push']['messages']['answer'] == "Python is a language."
        assert first_call_args['$push']['messages']['execution_time'] == 5.2

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_updates_title(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_col.update_one.return_value = mock_result
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        repo.save_message("abc123", "What is Python?", "Answer", 1.0)

        second_call = mock_col.update_one.call_args_list[1]
        assert second_call[0][0] == {'id': 'abc123', 'title': 'Slack Chat'}
        assert second_call[0][1]['$set']['title'] == "What is Python?"

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_chat_not_found(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_col.update_one.return_value = mock_result
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        result = repo.save_message("nonexistent", "Question", "Answer", 1.0)

        assert result is False

    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_message_db_unavailable(self, mock_cached):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = False
        repo = BotChatRepository()
        result = repo.save_message("abc123", "Question", "Answer", 1.0)

        assert result is False


class TestAuggieSessionId:

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_auggie_session_id_success(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        result = repo.save_auggie_session_id("abc123", "session-xyz")

        assert result is True
        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args[0][1]['$set']
        assert call_args['auggie_session_id'] == 'session-xyz'

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_auggie_session_id_no_chat_id(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_collection_fn.return_value = MagicMock()
        repo = BotChatRepository()
        result = repo.save_auggie_session_id("", "session-xyz")

        assert result is False

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_save_auggie_session_id_no_session_id(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_collection_fn.return_value = MagicMock()
        repo = BotChatRepository()
        result = repo.save_auggie_session_id("abc123", "")

        assert result is False

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_auggie_session_id_exists(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_col.find_one.return_value = {'id': 'abc123', 'auggie_session_id': 'session-xyz'}
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        result = repo.get_auggie_session_id("abc123")

        assert result == 'session-xyz'

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_auggie_session_id_not_found(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection_fn.return_value = mock_col

        repo = BotChatRepository()
        result = repo.get_auggie_session_id("nonexistent")

        assert result is None

    @patch('backend.services.slack.bot_chat_repository.get_bot_chats_collection')
    @patch('backend.services.base_repository.is_db_available_cached')
    def test_get_auggie_session_id_no_chat_id(self, mock_cached, mock_collection_fn):
        from backend.services.slack.bot_chat_repository import BotChatRepository

        mock_cached.return_value = True
        mock_collection_fn.return_value = MagicMock()
        repo = BotChatRepository()
        result = repo.get_auggie_session_id("")

        assert result is None


class TestBotChatContext:

    def test_dataclass_creation(self):
        from backend.services.slack.bot_chat_repository import BotChatContext

        ctx = BotChatContext(
            chat_id="abc123",
            user_id="U123",
            channel_id="C456",
            thread_ts="1234567890.123",
            auggie_session_id="session-xyz"
        )

        assert ctx.chat_id == "abc123"
        assert ctx.user_id == "U123"
        assert ctx.channel_id == "C456"
        assert ctx.thread_ts == "1234567890.123"
        assert ctx.auggie_session_id == "session-xyz"

    def test_dataclass_defaults(self):
        from backend.services.slack.bot_chat_repository import BotChatContext

        ctx = BotChatContext(chat_id="abc123", user_id="U123", channel_id="C456")

        assert ctx.thread_ts is None
        assert ctx.auggie_session_id is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

