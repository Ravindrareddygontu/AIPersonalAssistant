import os
import re
import json
import logging
from typing import List, Optional, Pattern, Dict

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
    'Tip:',
    '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏',
]

CODEX_RESPONSE_MARKER = '•'
CODEX_USER_INPUT_MARKER = '›'
CODEX_TOOL_CONNECTOR = '└'


class CodexProvider(TerminalAgentProvider):
    _session_ids: Dict[str, str] = {}

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
            re.compile(r'turn\.completed'),
            re.compile(r'Done\.'),
            re.compile(r'Finished'),
        ]

    def get_command(self, workspace: str, model: Optional[str] = None, message: str = None) -> List[str]:
        codex_cmd = self._find_codex_binary()
        session_key = f"{workspace}:{model or 'default'}"
        session_id = self._session_ids.get(session_key)

        if session_id:
            cmd = [codex_cmd, 'exec', '--json', 'resume', session_id]
        else:
            cmd = [codex_cmd, 'exec', '--json']

        if model:
            cmd.extend(['--model', model])
        if message:
            cmd.append(message)
        return cmd

    def get_session_id(self, workspace: str, model: Optional[str] = None) -> Optional[str]:
        session_key = f"{workspace}:{model or 'default'}"
        return self._session_ids.get(session_key)

    def store_session_id(self, workspace: str, model: Optional[str], session_id: str):
        session_key = f"{workspace}:{model or 'default'}"
        if self._session_ids.get(session_key) != session_id:
            self._session_ids[session_key] = session_id
            log.info(f"[CODEX] Stored session ID {session_id} for {session_key}")

    def clear_session(self, workspace: str, model: Optional[str] = None):
        session_key = f"{workspace}:{model or 'default'}"
        if session_key in self._session_ids:
            del self._session_ids[session_key]
            log.info(f"[CODEX] Cleared session for {session_key}")

    @property
    def is_exec_mode(self) -> bool:
        return True

    @property
    def uses_json_output(self) -> bool:
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
        return [CODEX_RESPONSE_MARKER]

    def get_thinking_marker(self) -> Optional[str]:
        return None

    def get_continuation_marker(self) -> Optional[str]:
        return CODEX_TOOL_CONNECTOR

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
            'i\'m checking',
            'explored',
            CODEX_TOOL_CONNECTOR,
            'reading file',
            'writing file',
            'searching',
            'running command',
            'executing',
        ]

    def get_status_patterns(self) -> List[str]:
        # Codex status lines start with • - we detect by prefix and stream as-is
        return ['•']

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
                if stripped.startswith(CODEX_TOOL_CONNECTOR) and in_response:
                    c = stripped[len(CODEX_TOOL_CONNECTOR):].strip()
                    if c:
                        content.append(f"↳ {c}")
                    continue

                if any(skip in stripped for skip in CODEX_SKIP_PATTERNS):
                    continue

                if in_response and stripped:
                    content.append(stripped)

        return '\n'.join(content) if content else None

