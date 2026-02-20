import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Pattern

log = logging.getLogger('terminal_agent.base')


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

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
        """Return the CLI command to start the agent as a list of arguments."""
        ...

    @abstractmethod
    def get_prompt_patterns(self) -> List[Pattern]:
        """Patterns that indicate the agent is ready for input."""
        ...

    @abstractmethod
    def get_end_patterns(self) -> List[Pattern]:
        """Patterns that indicate response is complete."""
        ...

    @abstractmethod
    def get_response_markers(self) -> List[str]:
        """Markers that indicate the start of actual response content (e.g., '●' for Auggie)."""
        ...

    @abstractmethod
    def get_activity_indicators(self) -> List[str]:
        """Indicators that the agent is still processing (extend timeout)."""
        ...

    @abstractmethod
    def get_skip_patterns(self) -> List[str]:
        """Patterns to skip when extracting response content."""
        ...

    @abstractmethod
    def sanitize_message(self, message: str) -> str:
        """Sanitize user message before sending to terminal."""
        ...

    @abstractmethod
    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        """Extract the actual response content from raw terminal output."""
        ...

    def get_tool_executing_patterns(self) -> List[str]:
        """Patterns indicating tools are executing (extended timeout)."""
        return [
            'Executing tools',
            'executing tools',
            'Reading file',
            'Searching',
        ]

    def get_status_patterns(self) -> List[str]:
        """Patterns to detect for frontend status display.
        Override in subclass to provide provider-specific patterns.
        """
        return []

    def get_thinking_marker(self) -> Optional[str]:
        """Marker for internal reasoning/thinking (e.g., '~' for Auggie)."""
        return None

    def get_continuation_marker(self) -> Optional[str]:
        """Marker for tool results/continuations (e.g., '⎿' for Auggie, '└' for Codex)."""
        return None

    @property
    def is_exec_mode(self) -> bool:
        """Return True if provider uses exec mode (one-shot command per message)."""
        return False

    @property
    def uses_json_output(self) -> bool:
        """Return True if provider outputs JSONL format."""
        return False

    def get_env(self) -> dict:
        """Get environment variables for the agent process."""
        import os
        env = os.environ.copy()
        env.update(self.config.env_vars)
        env['TERM'] = 'xterm-256color'
        env['COLUMNS'] = '200'
        env['LINES'] = '50'
        return env

