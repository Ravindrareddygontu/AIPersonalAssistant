import os
import re
import signal
import json
import logging
from typing import List, Dict

log = logging.getLogger('config')

# Ignore SIGPIPE to prevent broken pipe errors when client disconnects
signal.signal(signal.SIGPIPE, signal.SIG_IGN)

# =============================================================================
# Terminal Output Filtering Patterns
# =============================================================================

# Patterns to skip when parsing auggie terminal output
# These are UI hints, status messages, and metadata that shouldn't appear in responses
SKIP_PATTERNS: List[str] = [
    # UI hints and instructions
    'You can ask questions', 'edit files, or run commands',
    'Use Ctrl + Enter', 'Use vim mode', 'For automation',
    'To get the most out', 'from a project directory',
    'Ctrl+P to enhance', 'Ctrl+S to stash',
    '? to show shortcuts', 'Get started',
    # Status messages
    'Indexing disabled', 'working directory',
    'Processing response...', 'Sending request...',
    'Receiving response', 'Summarizing conversation history',
    'Executing tools...',
    # Model/user info (shouldn't leak into responses)
    'Claude Opus', 'Version 0.',
    # Progress indicators
    '▇▇▇▇▇',
]

# Command/terminal indicators for detecting non-response content
# Used by SlackNotifier and other components to skip command-like lines
TERMINAL_COMMAND_INDICATORS: List[str] = [
    'Terminal -', '2>/dev/null', '||', '&&',
    'grep ', 'lsof ', 'netstat ', 'ps aux',
    'cd ', '$ ', '# ', '```'
]

# Regex pattern matching lines containing only box-drawing and block characters
# Used to filter out terminal UI borders and decorations
BOX_CHARS_PATTERN = re.compile(r'^[╭╮╯╰│─╗╔║╚╝═█▇▆▅▄▃▂▁░▒▓\s]+$')

# Default workspace path for bots and terminal sessions
DEFAULT_WORKSPACE_PATH = os.environ.get('DEFAULT_WORKSPACE', os.path.expanduser("~/Projects/POC'S/ai-chat-app"))

# =============================================================================
# Bot Configuration
# =============================================================================

# Session timeout - kill idle sessions and reset session tracking after this time
BOT_SESSION_TIMEOUT_MINUTES = 30

# Maximum title length for chat titles
BOT_TITLE_MAX_LENGTH = 50

# Maximum message length per platform
BOT_MAX_MESSAGE_LENGTH_SLACK = 2900    # Slack limit is ~3000
BOT_MAX_MESSAGE_LENGTH_TELEGRAM = 4000  # Telegram limit is 4096
BOT_MAX_MESSAGE_LENGTH_DEFAULT = 4000   # Default for other platforms

# =============================================================================
# Storage Configuration
# =============================================================================

# File-based storage (default)
FILE_STORAGE_BASE_DIR = os.environ.get('FILE_STORAGE_DIR',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'))
FILE_STORAGE_ENABLED = os.environ.get('FILE_STORAGE_ENABLED', 'true').lower() == 'true'

# MongoDB Configuration (legacy, used for migration)
MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
MONGODB_DB_NAME = os.environ.get('MONGODB_DB_NAME', 'ai_chat_app')

# OpenAI API Configuration (for Whisper speech-to-text)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# Legacy file-based storage (kept for reference)
CHATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chats')
os.makedirs(CHATS_DIR, exist_ok=True)


# AI Provider options
AI_PROVIDERS = ['auggie', 'openai', 'codex']
TERMINAL_AGENT_PROVIDERS = ['auggie', 'codex']
DEFAULT_AI_PROVIDER = os.environ.get('DEFAULT_AI_PROVIDER', 'auggie').strip().lower()
if DEFAULT_AI_PROVIDER not in AI_PROVIDERS:
    DEFAULT_AI_PROVIDER = 'auggie'

# Available AI models - display names mapped to auggie model IDs
AVAILABLE_MODELS = [
    'claude-opus-4.5',
    'claude-sonnet-4',
    'gpt-4o',
    'gpt-4-turbo',
]
DEFAULT_MODEL = 'claude-opus-4.5'

# OpenAI models for direct API access (current as of Feb 2026)
OPENAI_MODELS = [
    'gpt-5.2',
    'gpt-5.2-chat-latest',
    'gpt-5.1',
    'gpt-5-mini',
    'gpt-5-nano',
]
DEFAULT_OPENAI_MODEL = 'gpt-5.2'

# Mapping from display model names to auggie CLI model IDs
MODEL_ID_MAP = {
    'claude-opus-4.5': 'opus4.5',
    'claude-sonnet-4': 'sonnet4',
    'gpt-4o': 'gpt-4o',
    'gpt-4-turbo': 'gpt-4-turbo',
}

def get_auggie_model_id(display_name):
    return MODEL_ID_MAP.get(display_name, display_name)


class Settings:
    def __init__(self):
        self._workspace = os.environ.get('DEFAULT_WORKSPACE', os.path.expanduser("~/Projects/POC'S/ai-chat-app"))
        self._model = DEFAULT_MODEL
        self._history_enabled = True  # Global toggle for chat history storage
        self._slack_notify = False  # Send status to Slack after completion
        self._slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '')
        self._ai_provider = DEFAULT_AI_PROVIDER  # 'auggie' or 'openai'
        self._openai_model = DEFAULT_OPENAI_MODEL  # Model for OpenAI provider

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

    @property
    def ai_provider(self):
        return self._ai_provider

    @ai_provider.setter
    def ai_provider(self, value):
        if value in AI_PROVIDERS:
            self._ai_provider = value

    @property
    def openai_model(self):
        return self._openai_model

    @openai_model.setter
    def openai_model(self, value):
        if value in OPENAI_MODELS:
            self._openai_model = value

    def to_dict(self):
        return {
            'workspace': self._workspace,
            'model': self._model,
            'available_models': AVAILABLE_MODELS,
            'history_enabled': self._history_enabled,
            'slack_notify': self._slack_notify,
            'slack_webhook_url': self._slack_webhook_url,
            'ai_provider': self._ai_provider,
            'ai_providers': AI_PROVIDERS,
            'openai_model': self._openai_model,
            'openai_models': OPENAI_MODELS,
        }


settings = Settings()


# =============================================================================
# Slack Integration Configuration
# =============================================================================

# Slack tokens (set via environment variables for security)
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')  # xoxb-...
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')  # xapp-... (only for Socket Mode)
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')  # For verifying webhook requests
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')  # Channel/DM ID to poll

# Default workspace for Slack commands (can be overridden)
SLACK_WORKSPACE = os.environ.get('SLACK_WORKSPACE', os.path.expanduser("~/Projects/POC'S/ai-chat-app"))

# Default model for Slack commands
SLACK_MODEL = os.environ.get('SLACK_MODEL', DEFAULT_MODEL)

# Enable/disable Slack bot on startup
SLACK_ENABLED = os.environ.get('SLACK_ENABLED', 'false').lower() == 'true'

# Slack integration mode: 'socket', 'poller', or 'http'
# - socket: Uses Bolt Socket Mode (WebSocket, good for development)
# - poller: Simple polling (no webhooks needed)
# - http: Uses webhook URLs (requires public HTTPS endpoint)
SLACK_MODE = os.environ.get('SLACK_MODE', 'socket')
