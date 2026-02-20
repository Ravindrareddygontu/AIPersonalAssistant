"""
Tests for telegram/bot.py - Telegram bot service.

Tests cover:
- TelegramBotConfig initialization and properties
- TelegramBot message handling
- TelegramBot command handling
- create_telegram_bot factory function
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.bots.telegram.bot import TelegramBotConfig, TelegramBot, create_telegram_bot


class TestTelegramBotConfig:

    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            config = TelegramBotConfig()
            assert config.bot_token is None
            assert config.model is None

    def test_env_vars_loaded(self):
        env = {
            'TELEGRAM_BOT_TOKEN': 'test-token-123',
            'TELEGRAM_WORKSPACE': '/test/workspace',
            'TELEGRAM_MODEL': 'claude-opus-4.5'
        }
        with patch.dict(os.environ, env, clear=True):
            config = TelegramBotConfig()
            assert config.bot_token == 'test-token-123'
            assert config.workspace == '/test/workspace'
            assert config.model == 'claude-opus-4.5'

    def test_explicit_values_override_env(self):
        env = {'TELEGRAM_BOT_TOKEN': 'env-token'}
        with patch.dict(os.environ, env, clear=True):
            config = TelegramBotConfig(bot_token='explicit-token')
            assert config.bot_token == 'explicit-token'

    def test_is_configured_true(self):
        config = TelegramBotConfig(bot_token='valid-token')
        assert config.is_configured is True

    def test_is_configured_false(self):
        with patch.dict(os.environ, {}, clear=True):
            config = TelegramBotConfig(bot_token=None)
            assert config.is_configured is False


class TestTelegramBotExtractSummary:

    def test_extract_summary_with_tags(self):
        bot = TelegramBot(TelegramBotConfig())
        content = "Some content\n---SUMMARY---\nThis is summary\n---END_SUMMARY---\nMore content"
        clean, summary = bot.extract_summary(content)
        assert summary == "This is summary"
        assert "---SUMMARY---" not in clean

    def test_extract_summary_no_tags(self):
        bot = TelegramBot(TelegramBotConfig())
        content = "Just regular content"
        clean, summary = bot.extract_summary(content)
        assert clean == "Just regular content"
        assert summary is None


class TestTelegramBotHandleMessage:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = TelegramBotConfig(workspace='/test/workspace')
        self.bot = TelegramBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()

    @pytest.mark.asyncio
    async def test_empty_message_prompts_user(self):
        update = MagicMock()
        update.message.text = "   "
        update.message.reply_text = AsyncMock()

        await self.bot._handle_message(update, MagicMock())
        update.message.reply_text.assert_called_with("Please provide a message!")

    @pytest.mark.asyncio
    async def test_successful_response(self):
        response = MagicMock()
        response.success = True
        response.content = "Test response"
        response.execution_time = 5.0
        response.session_id = None
        self.bot._executor.execute.return_value = response

        update = MagicMock()
        update.message.text = "Test question"
        update.effective_chat.id = 12345
        update.effective_user.id = 67890
        thinking_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=thinking_msg)

        await self.bot._handle_message(update, MagicMock())

        self.bot._executor.execute.assert_called_once_with(
            message="Test question",
            workspace='/test/workspace',
            model=None,
            source='bot',
            session_id=None
        )
        assert thinking_msg.edit_text.called
        final_call = thinking_msg.edit_text.call_args_list[-1]
        assert "Test response" in str(final_call)

    @pytest.mark.asyncio
    async def test_failed_response(self):
        response = MagicMock()
        response.success = False
        response.error = "Test error"
        response.execution_time = 1.0
        self.bot._executor.execute.return_value = response

        update = MagicMock()
        update.message.text = "Test"
        update.effective_chat.id = 12345
        update.effective_user.id = 67890
        thinking_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=thinking_msg)

        await self.bot._handle_message(update, MagicMock())

        call_args = thinking_msg.edit_text.call_args[0][0]
        assert "Error" in call_args


class TestTelegramBotCommands:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = TelegramBotConfig(workspace='/test/workspace')
        self.bot = TelegramBot(self.config)

    @pytest.mark.asyncio
    async def test_start_command(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        await self.bot._handle_start(update, MagicMock())

        call_args = update.message.reply_text.call_args[0][0]
        assert "Auggie Bot" in call_args
        assert "/help" in call_args

    @pytest.mark.asyncio
    async def test_help_command(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        await self.bot._handle_help(update, MagicMock())

        call_args = update.message.reply_text.call_args[0][0]
        assert "Help" in call_args
        assert "/status" in call_args

    @pytest.mark.asyncio
    async def test_status_command(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        await self.bot._handle_status(update, MagicMock())

        call_args = update.message.reply_text.call_args[0][0]
        assert "running" in call_args.lower()
        assert self.config.workspace in call_args


class TestCreateTelegramBot:

    def test_creates_bot_with_config(self):
        bot = create_telegram_bot(
            bot_token='test-token',
            workspace='/custom/path',
            model='gpt-4'
        )
        assert isinstance(bot, TelegramBot)
        assert bot.config.bot_token == 'test-token'
        assert bot.config.workspace == '/custom/path'
        assert bot.config.model == 'gpt-4'

    def test_creates_bot_with_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            bot = create_telegram_bot()
            assert isinstance(bot, TelegramBot)
            assert bot.config.bot_token is None


class TestTelegramBotInitialization:

    def test_bot_creates_default_config_when_none(self):
        with patch.dict(os.environ, {}, clear=True):
            bot = TelegramBot(config=None)
            assert bot.config is not None
            assert isinstance(bot.config, TelegramBotConfig)

    def test_bot_initial_state(self):
        bot = TelegramBot(TelegramBotConfig())
        assert bot._application is None
        assert bot._executor is None
        assert bot._running is False

    def test_run_polling_requires_token(self):
        with patch.dict(os.environ, {}, clear=True):
            config = TelegramBotConfig(bot_token=None)
        bot = TelegramBot(config)

        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            bot.run_polling()


class TestTelegramBotHelpText:

    def test_help_text_contains_commands(self):
        bot = TelegramBot(TelegramBotConfig())
        help_text = bot.get_help_text()

        assert "/start" in help_text
        assert "/help" in help_text
        assert "/status" in help_text

    def test_help_text_contains_examples(self):
        bot = TelegramBot(TelegramBotConfig())
        help_text = bot.get_help_text()

        assert "Examples" in help_text or "example" in help_text.lower()


class TestTelegramBotLongResponse:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = TelegramBotConfig(workspace='/test/workspace')
        self.bot = TelegramBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()
        self.bot._summarizer.summarize.return_value = "Summary"

    @pytest.mark.asyncio
    async def test_long_response_truncated(self):
        response = MagicMock()
        response.success = True
        response.content = "A" * 5000
        response.execution_time = 1.0
        response.session_id = None
        self.bot._executor.execute.return_value = response

        update = MagicMock()
        update.message.text = "Test"
        update.effective_chat.id = 12345
        update.effective_user.id = 67890
        thinking_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=thinking_msg)

        await self.bot._handle_message(update, MagicMock())

        call_args = thinking_msg.edit_text.call_args[0][0]
        assert "truncated" in call_args.lower()
        self.bot._summarizer.summarize.assert_called_once()


class TestTelegramBotExceptionHandling:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = TelegramBotConfig(workspace='/test/workspace')
        self.bot = TelegramBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()

    @pytest.mark.asyncio
    async def test_handle_message_executor_exception(self):
        self.bot._executor.execute.side_effect = Exception("Connection failed")

        update = MagicMock()
        update.message.text = "Test"
        update.effective_chat.id = 12345
        update.effective_user.id = 67890
        thinking_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=thinking_msg)

        await self.bot._handle_message(update, MagicMock())

        call_args = thinking_msg.edit_text.call_args[0][0]
        assert "Error" in call_args
        assert "Connection failed" in call_args


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

