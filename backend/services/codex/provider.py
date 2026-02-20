import os
import re
import logging
from typing import List, Optional, Pattern

from backend.services.terminal_agent.base import (
    TerminalAgentProvider,
    TerminalAgentConfig,
)

log = logging.getLogger('codex.provider')


CODEX_SKIP_PATTERNS: List[str] = [
    'Codex CLI',
    'Press Enter',
    'Use /help',
    '/model',
    '/exit',
    'approval mode',
    'Suggest',
    'Auto Edit',
    'Full Auto',
    'GPT-5',
    'gpt-5',
    'Processing',
    'Thinking',
    '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏',
]


class CodexProvider(TerminalAgentProvider):

    def __init__(self):
        config = TerminalAgentConfig(
            name='codex',
            command='codex',
            default_model=None,
            supported_models=['gpt-5.3-codex', 'o3', 'o4-mini', 'gpt-5.2', 'gpt-5.1'],
            prompt_wait_timeout=60.0,
            max_execution_time=300.0,
            silence_timeout=10.0,
            data_silence_timeout=3.0,
        )
        super().__init__(config)
        self._prompt_patterns = [
            re.compile(r'›'),
            re.compile(r'context left'),
            re.compile(r'OpenAI Codex'),
        ]
        self._end_patterns = [
            re.compile(r'›'),
            re.compile(r'context left'),
            re.compile(r'Done\.'),
            re.compile(r'Finished'),
        ]

    def get_command(self, workspace: str, model: Optional[str] = None, message: str = None) -> List[str]:
        codex_cmd = self._find_codex_binary()
        cmd = [codex_cmd, 'exec']
        if model:
            cmd.extend(['--model', model])
        if message:
            cmd.append(message)
        return cmd

    @property
    def is_exec_mode(self) -> bool:
        return True

    def _find_codex_binary(self) -> str:
        for path in [
            '/home/dell/.nvm/versions/node/v22.22.0/bin/codex',
            os.path.expanduser('~/.nvm/versions/node/v22.22.0/bin/codex'),
            '/usr/local/bin/codex',
            '/usr/bin/codex',
        ]:
            if os.path.exists(path):
                return path
        return 'codex'

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
        return ['▸', '→', '•']

    def get_activity_indicators(self) -> List[str]:
        return [
            'Thinking...',
            'Processing...',
            'Analyzing...',
            'Searching...',
            'Reading...',
            'Writing...',
            '⠋', '⠙', '⠹', '⠸', '⠼', '⠴',
        ]

    def get_skip_patterns(self) -> List[str]:
        return CODEX_SKIP_PATTERNS

    def get_tool_executing_patterns(self) -> List[str]:
        return [
            'reading file',
            'writing file',
            'searching',
            'running command',
            'executing',
            'shell:',
            'edit:',
            'read:',
        ]

    def sanitize_message(self, message: str) -> str:
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        sanitized = re.sub(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞]', '', sanitized)
        return sanitized

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        lines = raw_output.split('\n')
        content = []
        in_response = False

        for line in lines:
            stripped = line.strip()
            if not stripped and not in_response:
                continue

            for marker in self.get_response_markers():
                if stripped.startswith(marker):
                    in_response = True
                    c = stripped[len(marker):].strip()
                    if c:
                        content.append(c)
                    break
            else:
                if any(skip in stripped for skip in CODEX_SKIP_PATTERNS):
                    continue

                if in_response and stripped:
                    content.append(stripped)

        return '\n'.join(content) if content else None

