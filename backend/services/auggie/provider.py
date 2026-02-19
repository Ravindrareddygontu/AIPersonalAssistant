import os
import re
import logging
from typing import List, Optional, Pattern

from backend.services.terminal_agent.base import (
    TerminalAgentProvider,
    TerminalAgentConfig,
)
from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN, get_auggie_model_id

log = logging.getLogger('auggie.provider')


class AuggieProvider(TerminalAgentProvider):

    def __init__(self):
        config = TerminalAgentConfig(
            name='auggie',
            command='auggie',
            default_model='claude-opus-4.5',
            supported_models=['claude-opus-4.5', 'claude-sonnet-4', 'gpt-4o', 'gpt-4-turbo'],
            prompt_wait_timeout=60.0,
            max_execution_time=300.0,
            silence_timeout=10.0,
            data_silence_timeout=3.0,
        )
        super().__init__(config)
        self._prompt_patterns = [
            re.compile(r'›'),
            re.compile(r'>'),
        ]
        self._end_patterns = [
            re.compile(r'│ ›\s*│'),
            re.compile(r'╰─+╯'),
        ]

    def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
        auggie_cmd = self._find_auggie_binary()
        cmd = [auggie_cmd]
        if model:
            auggie_model_id = get_auggie_model_id(model)
            cmd.extend(['-m', auggie_model_id])
        return cmd

    def _find_auggie_binary(self) -> str:
        for path in [
            '/home/dell/.nvm/versions/node/v22.22.0/bin/auggie',
            os.path.expanduser('~/.nvm/versions/node/v22.22.0/bin/auggie'),
            '/usr/local/bin/auggie',
            '/usr/bin/auggie',
        ]:
            if os.path.exists(path):
                return path
        return 'auggie'

    def get_env(self) -> dict:
        env = super().get_env()
        nvm_bin = '/home/dell/.nvm/versions/node/v22.22.0/bin'
        if nvm_bin not in env.get('PATH', ''):
            env['PATH'] = nvm_bin + ':' + env.get('PATH', '/usr/bin:/bin')
        return env

    def get_prompt_patterns(self) -> List[Pattern]:
        return self._prompt_patterns

    def get_end_patterns(self) -> List[Pattern]:
        return self._end_patterns

    def get_response_markers(self) -> List[str]:
        return ['●']

    def get_activity_indicators(self) -> List[str]:
        return [
            'Receiving response...',
            'Sending request...',
            'Processing response...',
            'Executing tools...',
            'Summarizing conversation history...',
            '▇▇▇',
        ]

    def get_skip_patterns(self) -> List[str]:
        return SKIP_PATTERNS

    def get_tool_executing_patterns(self) -> List[str]:
        return [
            'Executing tools',
            'executing tools',
            '- read file',
            '- read directory',
            '- search',
            'Codebase search',
            'Terminal -',
            '↳ Read',
            '↳ Command',
            '↳ Search',
            'Reading file',
            'Searching',
        ]

    def sanitize_message(self, message: str) -> str:
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        sanitized = re.sub(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞]', '', sanitized)
        return (sanitized
            .replace('●', '*')
            .replace('•', '-')
            .replace('⎿', '|')
            .replace('›', '>')
            .replace('╭', '+')
            .replace('╮', '+')
            .replace('╯', '+')
            .replace('╰', '+')
            .replace('│', '|')
            .replace('─', '-'))

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        lines = raw_output.split('\n')
        content = []
        in_response = False

        for line in lines:
            stripped = line.strip()
            if not stripped and not in_response:
                continue

            if BOX_CHARS_PATTERN.match(stripped):
                continue

            if stripped.startswith('●'):
                in_response = True
                c = stripped[1:].strip()
                if c:
                    content.append(c)
                continue
            elif stripped.startswith('~'):
                continue
            elif stripped.startswith('⎿') and in_response:
                c = stripped[1:].strip()
                if c:
                    content.append(f"↳ {c}")
                continue

            if in_response and any(skip in stripped for skip in SKIP_PATTERNS):
                continue

            if in_response and stripped:
                if not any(skip in stripped for skip in ['Claude Opus', 'Version 0.']):
                    content.append(stripped)

        return '\n'.join(content) if content else None

