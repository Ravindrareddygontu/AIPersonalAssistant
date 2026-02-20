# Bot integrations for various messaging platforms
from .base import BaseBot, BaseBotConfig, BotResponse, ChatContext
from .slack import (
    SlackBot,
    SlackBotConfig,
    SlackPoller,
    SlackNotifier,
    create_slack_bot,
    notify_completion,
    CompletionStatus,
    SlackNotification,
)
from .telegram import (
    TelegramBot,
    TelegramBotConfig,
    create_telegram_bot,
    TelegramChatRepository,
    TelegramChatContext,
)

__all__ = [
    # Base
    'BaseBot',
    'BaseBotConfig',
    'BotResponse',
    'ChatContext',
    # Slack
    'SlackBot',
    'SlackBotConfig',
    'SlackPoller',
    'SlackNotifier',
    'create_slack_bot',
    'notify_completion',
    'CompletionStatus',
    'SlackNotification',
    # Telegram
    'TelegramBot',
    'TelegramBotConfig',
    'create_telegram_bot',
    'TelegramChatRepository',
    'TelegramChatContext',
]

