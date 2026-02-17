# Slack integration services
from .poller import SlackPoller
from .notifier import SlackNotifier, notify_completion, CompletionStatus, SlackNotification
from .bot import SlackBot, SlackBotConfig, create_slack_bot

__all__ = [
    'SlackPoller',
    'SlackNotifier',
    'notify_completion',
    'CompletionStatus',
    'SlackNotification',
    'SlackBot',
    'SlackBotConfig',
    'create_slack_bot',
]
