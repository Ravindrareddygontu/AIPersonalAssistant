import os
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Pattern

log = logging.getLogger('terminal_agent.base')

NVM_BIN_PATH = '/home/dell/.nvm/versions/node/v22.22.0/bin'
SPINNER_CHARS = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞'
SPINNER_PATTERN = re.compile(f'[{SPINNER_CHARS}]')


@dataclass
class TerminalAgentConfig:
    name: str
    command: str
    default_model: Optional[str] = None
    supported_models: List[str] = field(default_factory=list)
    env_vars: dict = field(default_factory=dict)
    prompt_wait_timeout: float = 60.0
    max_execution_time: float = 300.0
    silence_timeout: float = 10.0
    data_silence_timeout: float = 3.0


@dataclass
class TerminalAgentResponse:
    success: bool
    content: str
    error: Optional[str] = None
    execution_time: float = 0.0


class TerminalAgentProvider(ABC):

    def __init__(self, config: TerminalAgentConfig):
        self.config = config
        self._binary_path: Optional[str] = None

    @property
    def name(self) -> str:
        return self.config.name

    def _find_binary(self, name: str, extra_paths: Optional[List[str]] = None) -> str:
        paths = [
            os.path.join(NVM_BIN_PATH, name),
            os.path.expanduser(f'~/.nvm/versions/node/v22.22.0/bin/{name}'),
            f'/usr/local/bin/{name}',
            f'/usr/bin/{name}',
        ]
        if extra_paths:
            paths = extra_paths + paths
        for path in paths:
            if os.path.exists(path):
                return path
        return name

    def get_binary(self) -> str:
        if not self._binary_path:
            self._binary_path = self._find_binary(self.config.command)
        return self._binary_path

    @abstractmethod
    def get_command(self, workspace: str, model: Optional[str] = None, session_id: Optional[str] = None) -> List[str]:
        pass

    @abstractmethod
    def get_prompt_patterns(self) -> List[Pattern]:
        pass

    @abstractmethod
    def get_end_patterns(self) -> List[Pattern]:
        pass

    @abstractmethod
    def get_response_markers(self) -> List[str]:
        pass

    @abstractmethod
    def get_activity_indicators(self) -> List[str]:
        pass

    @abstractmethod
    def get_skip_patterns(self) -> List[str]:
        pass

    @abstractmethod
    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        pass

    def sanitize_message(self, message: str) -> str:
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        return SPINNER_PATTERN.sub('', sanitized)

    def get_tool_executing_patterns(self) -> List[str]:
        return [
            'Executing tools',
            'executing tools',
            'Reading file',
            'Searching',
        ]

    def get_status_patterns(self) -> List[str]:
        return []

    def get_thinking_marker(self) -> Optional[str]:
        return None

    def get_continuation_marker(self) -> Optional[str]:
        return None

    @property
    def is_exec_mode(self) -> bool:
        return False

    @property
    def uses_json_output(self) -> bool:
        return False

    def get_env(self) -> dict:
        env = os.environ.copy()
        if NVM_BIN_PATH not in env.get('PATH', ''):
            env['PATH'] = NVM_BIN_PATH + ':' + env.get('PATH', '/usr/bin:/bin')
        env.update(self.config.env_vars)
        env['TERM'] = 'xterm-256color'
        env['COLUMNS'] = '200'
        env['LINES'] = '50'
        return env

    def get_session_id(self, workspace: str, model: Optional[str] = None) -> Optional[str]:
        from backend.session.persistence import session_manager
        return session_manager.get_session(self.name, workspace, model)

    def store_session_id(self, workspace: str, session_id: str, model: Optional[str] = None):
        from backend.session.persistence import session_manager
        session_manager.store_session(self.name, workspace, session_id, model)

    def clear_session(self, workspace: str, model: Optional[str] = None):
        from backend.session.persistence import session_manager
        session_manager.clear_session(self.name, workspace, model)

    def session_exists(self, session_id: str) -> bool:
        from backend.session.persistence import session_manager
        return session_manager.session_exists(self.name, session_id)

