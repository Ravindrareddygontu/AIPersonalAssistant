import pytest
import sys
import os
import re
from typing import List, Optional, Pattern

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.terminal_agent.base import (
    TerminalAgentConfig,
    TerminalAgentResponse,
    TerminalAgentProvider,
)


class MockProvider(TerminalAgentProvider):

    def __init__(self):
        config = TerminalAgentConfig(
            name='mock',
            command='mock-cmd',
            default_model='default-model',
            supported_models=['model-a', 'model-b'],
            prompt_wait_timeout=30.0,
            max_execution_time=120.0,
        )
        super().__init__(config)
        self._prompt_patterns = [re.compile(r'>\s*$')]
        self._end_patterns = [re.compile(r'Done\.')]

    def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
        cmd = ['mock-cmd', '--workspace', workspace]
        if model:
            cmd.extend(['--model', model])
        return cmd

    def get_prompt_patterns(self) -> List[Pattern]:
        return self._prompt_patterns

    def get_end_patterns(self) -> List[Pattern]:
        return self._end_patterns

    def get_response_markers(self) -> List[str]:
        return ['●', '▸']

    def get_activity_indicators(self) -> List[str]:
        return ['Processing...', 'Thinking...']

    def get_skip_patterns(self) -> List[str]:
        return ['Skip this', 'Ignore this']

    def sanitize_message(self, message: str) -> str:
        return message.replace('\n', ' ').strip()

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        if '●' in raw_output:
            idx = raw_output.index('●')
            return raw_output[idx + 1:].strip()
        return None


class TestTerminalAgentConfig:

    def test_config_defaults(self):
        config = TerminalAgentConfig(name='test', command='test-cmd')
        assert config.name == 'test'
        assert config.command == 'test-cmd'
        assert config.default_model is None
        assert config.supported_models == []
        assert config.env_vars == {}
        assert config.prompt_wait_timeout == 60.0
        assert config.max_execution_time == 300.0

    def test_config_custom_values(self):
        config = TerminalAgentConfig(
            name='custom',
            command='custom-cmd',
            default_model='v1',
            supported_models=['v1', 'v2'],
            env_vars={'KEY': 'value'},
            prompt_wait_timeout=45.0,
            max_execution_time=180.0,
            silence_timeout=15.0,
        )
        assert config.name == 'custom'
        assert config.default_model == 'v1'
        assert 'v2' in config.supported_models
        assert config.env_vars['KEY'] == 'value'
        assert config.silence_timeout == 15.0


class TestTerminalAgentResponse:

    def test_response_success(self):
        response = TerminalAgentResponse(success=True, content='Hello world')
        assert response.success is True
        assert response.content == 'Hello world'
        assert response.error is None
        assert response.execution_time == 0.0

    def test_response_failure(self):
        response = TerminalAgentResponse(
            success=False,
            content='',
            error='Connection failed',
            execution_time=1.5
        )
        assert response.success is False
        assert response.error == 'Connection failed'
        assert response.execution_time == 1.5


class TestTerminalAgentProvider:

    def test_provider_name(self):
        provider = MockProvider()
        assert provider.name == 'mock'

    def test_provider_config(self):
        provider = MockProvider()
        assert provider.config.command == 'mock-cmd'
        assert provider.config.default_model == 'default-model'

    def test_get_command_basic(self):
        provider = MockProvider()
        cmd = provider.get_command('/home/user/project')
        assert cmd == ['mock-cmd', '--workspace', '/home/user/project']

    def test_get_command_with_model(self):
        provider = MockProvider()
        cmd = provider.get_command('/home/user/project', 'model-a')
        assert '--model' in cmd
        assert 'model-a' in cmd

    def test_get_prompt_patterns(self):
        provider = MockProvider()
        patterns = provider.get_prompt_patterns()
        assert len(patterns) == 1
        assert patterns[0].search('input> ')

    def test_get_response_markers(self):
        provider = MockProvider()
        markers = provider.get_response_markers()
        assert '●' in markers

    def test_sanitize_message(self):
        provider = MockProvider()
        result = provider.sanitize_message('  hello\nworld  ')
        assert result == 'hello world'

    def test_extract_response(self):
        provider = MockProvider()
        result = provider.extract_response('● This is the response', 'test')
        assert result == 'This is the response'

    def test_get_env_includes_term(self):
        provider = MockProvider()
        env = provider.get_env()
        assert 'TERM' in env
        assert env['TERM'] == 'xterm-256color'
        assert 'COLUMNS' in env


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

