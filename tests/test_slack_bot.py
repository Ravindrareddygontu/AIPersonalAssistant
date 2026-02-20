"""
Tests for slack/bot.py - Slack bot service.

Tests cover:
- SlackBotConfig initialization and properties
- SlackBot message extraction
- SlackBot message handling
- SlackBot slash command handling
- create_slack_bot factory function
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.slack.bot import SlackBotConfig, SlackBot, create_slack_bot
from backend.services.auggie.summarizer import AISummarizer


class TestSlackBotConfig:

    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig()
            assert config.bot_token is None
            assert config.app_token is None
            assert config.signing_secret is None
            assert config.model is None

    def test_env_vars_loaded(self):
        env = {
            'SLACK_BOT_TOKEN': 'xoxb-test-token',
            'SLACK_APP_TOKEN': 'xapp-test-token',
            'SLACK_SIGNING_SECRET': 'test-secret',
            'SLACK_WORKSPACE': '/test/workspace',
            'SLACK_MODEL': 'claude-opus-4.5'
        }
        with patch.dict(os.environ, env, clear=True):
            config = SlackBotConfig()
            assert config.bot_token == 'xoxb-test-token'
            assert config.app_token == 'xapp-test-token'
            assert config.signing_secret == 'test-secret'
            assert config.workspace == '/test/workspace'
            assert config.model == 'claude-opus-4.5'

    def test_explicit_values_override_env(self):
        env = {'SLACK_BOT_TOKEN': 'env-token'}
        with patch.dict(os.environ, env, clear=True):
            config = SlackBotConfig(bot_token='explicit-token')
            assert config.bot_token == 'explicit-token'

    def test_is_socket_mode_true(self):
        config = SlackBotConfig(app_token='xapp-valid-token')
        assert config.is_socket_mode is True

    def test_is_socket_mode_false_invalid_prefix(self):
        config = SlackBotConfig(app_token='invalid-token')
        assert config.is_socket_mode is False

    def test_is_socket_mode_false_none(self):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(app_token=None)
            assert config.is_socket_mode is False


class TestSlackBotExtractMessageText:

    def test_simple_text(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": "Hello world"}
        result = bot._extract_message_text(event)
        assert result == "Hello world"

    def test_removes_bot_mention(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": "<@U12345ABC> Hello world"}
        result = bot._extract_message_text(event)
        assert result == "Hello world"

    def test_removes_multiple_mentions(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": "<@U12345ABC> <@U67890DEF> Hello"}
        result = bot._extract_message_text(event)
        assert result == "Hello"

    def test_empty_text(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": ""}
        result = bot._extract_message_text(event)
        assert result == ""

    def test_only_mention(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": "<@U12345ABC>"}
        result = bot._extract_message_text(event)
        assert result == ""


class TestSlackBotHandleMessage:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = SlackBotConfig(workspace='/test/workspace')
        self.bot = SlackBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()
        self.say = MagicMock()
        self.client = MagicMock()

    def test_empty_message_prompts_user(self):
        event = {"text": "", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, self.say, self.client)
        self.say.assert_called_with("Please provide a message!", thread_ts="123.456")

    def test_successful_response(self):
        response = MagicMock()
        response.success = True
        response.content = "Test response"
        response.execution_time = 5.0
        self.bot._executor.execute.return_value = response

        event = {"text": "Test question", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, self.say, self.client)

        self.bot._executor.execute.assert_called_once_with(
            message="Test question",
            workspace='/test/workspace',
            model=None
        )
        assert self.say.call_count == 2  # thinking + response

    def test_failed_response(self):
        response = MagicMock()
        response.success = False
        response.error = "Test error"
        self.bot._executor.execute.return_value = response

        event = {"text": "Test", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, self.say, self.client)

        calls = self.say.call_args_list
        assert any("Error" in str(c) for c in calls)

    def test_uses_thread_ts_from_event(self):
        response = MagicMock()
        response.success = True
        response.content = "Response"
        response.execution_time = 1.0
        self.bot._executor.execute.return_value = response

        event = {"text": "Test", "channel": "C123", "thread_ts": "111.222", "ts": "333.444"}
        self.bot._handle_message(event, self.say, self.client)

        for call_args in self.say.call_args_list:
            assert call_args.kwargs.get('thread_ts') == "111.222"

    def test_long_response_truncated(self):
        response = MagicMock()
        response.success = True
        response.content = "A" * 3500
        response.execution_time = 1.0
        self.bot._executor.execute.return_value = response
        self.bot._summarizer.summarize.return_value = "Summary"

        event = {"text": "Test", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, self.say, self.client)

        calls = self.say.call_args_list
        final_call = calls[-1]
        assert "truncated" in str(final_call).lower()


class TestSlackBotHandleSlashCommand:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = SlackBotConfig(workspace='/test/workspace')
        self.bot = SlackBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()
        self.respond = MagicMock()

    def test_help_command(self):
        command = {"text": "help", "user_name": "testuser", "channel_id": "C123"}
        self.bot._handle_slash_command(self.respond, command)

        call_args = self.respond.call_args[0][0]
        assert "Auggie Bot" in call_args
        assert "/auggie" in call_args

    def test_empty_command_shows_help(self):
        command = {"text": "", "user_name": "testuser", "channel_id": "C123"}
        self.bot._handle_slash_command(self.respond, command)

        call_args = self.respond.call_args[0][0]
        assert "Auggie Bot" in call_args

    def test_status_command(self):
        command = {"text": "status", "user_name": "testuser", "channel_id": "C123"}
        self.bot._handle_slash_command(self.respond, command)

        call_args = self.respond.call_args[0][0]
        assert "running" in call_args.lower()
        assert self.config.workspace in call_args

    def test_executes_regular_command(self):
        response = MagicMock()
        response.success = True
        response.content = "Command result"
        response.execution_time = 2.0
        self.bot._executor.execute.return_value = response

        command = {"text": "list files", "user_name": "testuser", "channel_id": "C123"}
        self.bot._handle_slash_command(self.respond, command)

        self.bot._executor.execute.assert_called_once_with(
            message="list files",
            workspace='/test/workspace',
            model=None
        )

    def test_command_error_response(self):
        response = MagicMock()
        response.success = False
        response.error = "Command failed"
        self.bot._executor.execute.return_value = response

        command = {"text": "invalid", "user_name": "testuser", "channel_id": "C123"}
        self.bot._handle_slash_command(self.respond, command)

        calls = self.respond.call_args_list
        assert any("Error" in str(c) for c in calls)


class TestCreateSlackBot:

    def test_creates_bot_with_config(self):
        bot = create_slack_bot(
            bot_token='xoxb-test',
            app_token='xapp-test',
            workspace='/custom/path',
            model='gpt-4'
        )
        assert isinstance(bot, SlackBot)
        assert bot.config.bot_token == 'xoxb-test'
        assert bot.config.app_token == 'xapp-test'
        assert bot.config.workspace == '/custom/path'
        assert bot.config.model == 'gpt-4'

    def test_creates_bot_with_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            bot = create_slack_bot()
            assert isinstance(bot, SlackBot)
            assert bot.config.bot_token is None


class TestSlackBotSocketMode:

    def test_socket_mode_requires_app_token(self):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test', app_token=None)
        bot = SlackBot(config)

        with pytest.raises(ValueError, match="Socket Mode requires"):
            bot.start_socket_mode()

    def test_socket_mode_requires_valid_prefix(self):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test', app_token='invalid')
        bot = SlackBot(config)

        with pytest.raises(ValueError, match="Socket Mode requires"):
            bot.start_socket_mode()


class TestSlackBotExceptionHandling:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = SlackBotConfig(workspace='/test/workspace')
        self.bot = SlackBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()

    def test_handle_message_executor_exception(self):
        self.bot._executor.execute.side_effect = Exception("Connection failed")
        say = MagicMock()

        event = {"text": "Test", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, say, MagicMock())

        calls = say.call_args_list
        error_call = [c for c in calls if "Error" in str(c)]
        assert len(error_call) > 0
        assert "Connection failed" in str(error_call[0])

    def test_handle_slash_command_executor_exception(self):
        self.bot._executor.execute.side_effect = Exception("Timeout error")
        respond = MagicMock()

        command = {"text": "test command", "user_name": "user", "channel_id": "C123"}
        self.bot._handle_slash_command(respond, command)

        calls = respond.call_args_list
        error_call = [c for c in calls if "Error" in str(c)]
        assert len(error_call) > 0
        assert "Timeout error" in str(error_call[0])


class TestSlackBotSlashCommandTruncation:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = SlackBotConfig(workspace='/test/workspace')
        self.bot = SlackBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()

    def test_long_slash_response_truncated(self):
        response = MagicMock()
        response.success = True
        response.content = "B" * 3500
        response.execution_time = 3.0
        self.bot._executor.execute.return_value = response
        self.bot._summarizer.summarize.return_value = "Long content summary"
        respond = MagicMock()

        command = {"text": "generate report", "user_name": "user", "channel_id": "C123"}
        self.bot._handle_slash_command(respond, command)

        calls = respond.call_args_list
        final_call = str(calls[-1])
        assert "truncated" in final_call.lower()
        self.bot._summarizer.summarize.assert_called_once()


class TestSlackBotHelpText:

    def test_help_text_contains_commands(self):
        bot = SlackBot(SlackBotConfig())
        help_text = bot._get_help_text()

        assert "/auggie" in help_text
        assert "help" in help_text.lower()
        assert "status" in help_text.lower()
        assert "DM" in help_text or "Direct Message" in help_text

    def test_help_text_contains_examples(self):
        bot = SlackBot(SlackBotConfig())
        help_text = bot._get_help_text()

        assert "Examples" in help_text or "example" in help_text.lower()


class TestSlackBotInitialization:

    def test_bot_creates_default_config_when_none(self):
        with patch.dict(os.environ, {}, clear=True):
            bot = SlackBot(config=None)
            assert bot.config is not None
            assert isinstance(bot.config, SlackBotConfig)

    def test_bot_initial_state(self):
        bot = SlackBot(SlackBotConfig())
        assert bot._app is None
        assert bot._handler is None
        assert bot._executor is None
        assert bot._running is False

    @patch('slack_bolt.App')
    @patch('backend.services.auggie.AuggieExecutor')
    def test_ensure_initialized_creates_app(self, mock_executor, mock_app):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test', signing_secret='secret')
        bot = SlackBot(config)

        bot._ensure_initialized()

        mock_app.assert_called_once_with(token='xoxb-test', signing_secret='secret')
        assert bot._app is not None

    @patch('slack_bolt.App')
    @patch('backend.services.auggie.AuggieExecutor')
    def test_ensure_initialized_only_once(self, mock_executor, mock_app):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test')
        bot = SlackBot(config)

        bot._ensure_initialized()
        bot._ensure_initialized()

        assert mock_app.call_count == 1

    @patch('slack_bolt.App')
    @patch('backend.services.auggie.AuggieExecutor')
    def test_app_property_triggers_initialization(self, mock_executor, mock_app):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test')
        bot = SlackBot(config)

        _ = bot.app

        mock_app.assert_called_once()


class TestSlackBotStop:

    def test_stop_sets_running_false(self):
        bot = SlackBot(SlackBotConfig())
        bot._running = True
        bot._handler = None

        bot.stop()

        assert bot._running is False

    def test_stop_closes_handler(self):
        bot = SlackBot(SlackBotConfig())
        bot._handler = MagicMock()
        bot._running = True

        bot.stop()

        bot._handler.close.assert_called_once()


class TestSlackBotMessageFiltering:

    def test_extract_text_with_missing_text_key(self):
        bot = SlackBot(SlackBotConfig())
        event = {}
        result = bot._extract_message_text(event)
        assert result == ""

    def test_extract_text_preserves_content_after_mention(self):
        bot = SlackBot(SlackBotConfig())
        event = {"text": "<@U123ABC>   multiple   spaces   here"}
        result = bot._extract_message_text(event)
        assert result == "multiple   spaces   here"


class TestSlackBotEdgeCases:

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            self.config = SlackBotConfig(workspace='/test/workspace')
        self.bot = SlackBot(self.config)
        self.bot._executor = MagicMock()
        self.bot._summarizer = MagicMock()

    def test_response_with_none_content(self):
        response = MagicMock()
        response.success = True
        response.content = None
        response.execution_time = 1.0
        self.bot._executor.execute.return_value = response
        say = MagicMock()

        event = {"text": "Test", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, say, MagicMock())

        calls = say.call_args_list
        final_call = str(calls[-1])
        assert "1.0s" in final_call

    def test_response_with_empty_content(self):
        response = MagicMock()
        response.success = True
        response.content = ""
        response.execution_time = 2.0
        self.bot._executor.execute.return_value = response
        say = MagicMock()

        event = {"text": "Test", "channel": "C123", "ts": "123.456"}
        self.bot._handle_message(event, say, MagicMock())

        calls = say.call_args_list
        assert len(calls) == 2

    def test_status_command_case_insensitive(self):
        respond = MagicMock()
        for variant in ["STATUS", "Status", "sTaTuS"]:
            respond.reset_mock()
            command = {"text": variant, "user_name": "user", "channel_id": "C123"}
            self.bot._handle_slash_command(respond, command)
            assert "running" in str(respond.call_args).lower()

    def test_help_command_case_insensitive(self):
        respond = MagicMock()
        for variant in ["HELP", "Help", "hElP"]:
            respond.reset_mock()
            command = {"text": variant, "user_name": "user", "channel_id": "C123"}
            self.bot._handle_slash_command(respond, command)
            assert "Auggie Bot" in str(respond.call_args)

    def test_message_uses_ts_when_no_thread_ts(self):
        response = MagicMock()
        response.success = True
        response.content = "Response"
        response.execution_time = 1.0
        self.bot._executor.execute.return_value = response
        say = MagicMock()

        event = {"text": "Test", "channel": "C123", "ts": "999.888"}
        self.bot._handle_message(event, say, MagicMock())

        for call_args in say.call_args_list:
            assert call_args.kwargs.get('thread_ts') == "999.888"


class TestSlackBotNonBlockingMode:

    @patch('slack_bolt.App')
    @patch('slack_bolt.adapter.socket_mode.SocketModeHandler')
    @patch('backend.services.auggie.AuggieExecutor')
    def test_start_socket_mode_non_blocking(self, mock_executor, mock_handler_class, mock_app):
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig(bot_token='xoxb-test', app_token='xapp-valid-token')
        bot = SlackBot(config)

        bot.start_socket_mode(blocking=False)

        assert bot._running is True
        assert bot._thread is not None


class TestSlackBotImportError:

    def test_ensure_initialized_raises_import_error(self):
        with patch.dict(os.environ, {}, clear=True):
            config = SlackBotConfig()
        bot = SlackBot(config)

        with patch.dict('sys.modules', {'slack_bolt': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module")):
                with pytest.raises(ImportError, match="pip install slack-bolt"):
                    bot._ensure_initialized()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

