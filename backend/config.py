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
    '▇▇▇▇▇', '? to show shortcuts', 'Get started',
]

BOX_CHARS_PATTERN = re.compile(r'^[╭╮╯╰│─╗╔║╚╝═█▇▆▅▄▃▂▁░▒▓\s]+$')

CHATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chats')
os.makedirs(CHATS_DIR, exist_ok=True)


class Settings:
    def __init__(self):
        self._workspace = os.path.expanduser('~')

    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, value):
        self._workspace = os.path.expanduser(value)

    def to_dict(self):
        return {'workspace': self._workspace}


settings = Settings()

