import os
import re
import signal

signal.signal(signal.SIGPIPE, signal.SIG_IGN)

SKIP_PATTERNS = [
    'You can ask questions', 'edit files, or run commands',
    'Use Ctrl + Enter', 'Use vim mode', 'For automation',
    'Indexing disabled', 'working directory', 'To get the most out',
    'from a project directory', 'Ctrl+P to enhance', 'Ctrl+S to stash',
    'Claude Opus', 'Version 0.', '@veefin.com', '@gmail.com', 'ravindrar@',
    'Processing response...', 'esc to interrupt', 'Sending request...',
    'Receiving response', 'Summarizing conversation history',
    '▇▇▇▇▇', '? to show shortcuts', 'Get started',
    'Executing tools...',
]

BOX_CHARS_PATTERN = re.compile(r'^[╭╮╯╰│─╗╔║╚╝═█▇▆▅▄▃▂▁░▒▓\s]+$')

# MongoDB Configuration
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
MONGODB_DB_NAME = os.environ.get('MONGODB_DB_NAME', 'ai_chat_app')

# Legacy file-based storage (kept for reference, no longer used)
CHATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chats')
os.makedirs(CHATS_DIR, exist_ok=True)


# Available AI models - display names mapped to auggie model IDs
AVAILABLE_MODELS = [
    'claude-opus-4.5',
    'claude-sonnet-4',
    'gpt-4o',
    'gpt-4-turbo',
]
DEFAULT_MODEL = 'claude-opus-4.5'

# Mapping from display model names to auggie CLI model IDs
MODEL_ID_MAP = {
    'claude-opus-4.5': 'opus4.5',
    'claude-sonnet-4': 'sonnet4',
    'gpt-4o': 'gpt-4o',
    'gpt-4-turbo': 'gpt-4-turbo',
}

def get_auggie_model_id(display_name):
    """Convert display model name to auggie CLI model ID."""
    return MODEL_ID_MAP.get(display_name, display_name)


class Settings:
    def __init__(self):
        self._workspace = os.path.expanduser("~/Projects/POC'S/ai-chat-app")
        self._model = DEFAULT_MODEL
        self._history_enabled = True  # Global toggle for chat history storage
        self._slack_notify = False  # Send status to Slack after completion
        self._slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '')

    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, value):
        self._workspace = os.path.expanduser(value)

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        if value in AVAILABLE_MODELS:
            self._model = value

    @property
    def history_enabled(self):
        return self._history_enabled

    @history_enabled.setter
    def history_enabled(self, value):
        self._history_enabled = bool(value)

    @property
    def slack_notify(self):
        return self._slack_notify

    @slack_notify.setter
    def slack_notify(self, value):
        self._slack_notify = bool(value)

    @property
    def slack_webhook_url(self):
        return self._slack_webhook_url

    @slack_webhook_url.setter
    def slack_webhook_url(self, value):
        self._slack_webhook_url = str(value) if value else ''

    def to_dict(self):
        return {
            'workspace': self._workspace,
            'model': self._model,
            'available_models': AVAILABLE_MODELS,
            'history_enabled': self._history_enabled,
            'slack_notify': self._slack_notify,
            'slack_webhook_url': self._slack_webhook_url
        }


settings = Settings()


# =============================================================================
# Slack Integration Configuration
# =============================================================================

# Slack tokens (set via environment variables for security)
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')  # xoxb-...
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')  # xapp-... (only for Socket Mode)
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')  # Channel/DM ID to poll

# Default workspace for Slack commands (can be overridden)
SLACK_WORKSPACE = os.environ.get('SLACK_WORKSPACE', os.path.expanduser("~/Projects/POC'S/ai-chat-app"))

# Default model for Slack commands
SLACK_MODEL = os.environ.get('SLACK_MODEL', DEFAULT_MODEL)

# Enable/disable Slack bot on startup
SLACK_ENABLED = os.environ.get('SLACK_ENABLED', 'false').lower() == 'true'


def is_slack_configured() -> bool:
    """Check if Slack integration is properly configured."""
    return bool(SLACK_BOT_TOKEN and SLACK_APP_TOKEN)
