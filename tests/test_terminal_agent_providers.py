import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.auggie.provider import AuggieProvider
from backend.services.codex.provider import CodexProvider


class TestAuggieProvider:

    def test_provider_name(self):
        provider = AuggieProvider()
        assert provider.name == 'auggie'

    def test_config_values(self):
        provider = AuggieProvider()
        assert provider.config.command in ['auggie', 'augment']
        assert provider.config.default_model == 'claude-opus-4.5'
        assert 'claude-sonnet-4' in provider.config.supported_models

    def test_get_command_basic(self):
        provider = AuggieProvider()
        cmd = provider.get_command('/home/user/project')
        assert 'auggie' in cmd[0] or 'augment' in cmd[0]

    def test_get_command_with_model(self):
        provider = AuggieProvider()
        cmd = provider.get_command('/home/user/project', 'claude-sonnet-4')
        assert '--model' in cmd or '-m' in cmd
        assert any('sonnet' in c for c in cmd)

    def test_get_prompt_patterns(self):
        provider = AuggieProvider()
        patterns = provider.get_prompt_patterns()
        assert len(patterns) > 0
        assert any(p.search('›') for p in patterns)

    def test_get_response_markers(self):
        provider = AuggieProvider()
        markers = provider.get_response_markers()
        assert '●' in markers

    def test_sanitize_message(self):
        provider = AuggieProvider()
        result = provider.sanitize_message('hello\nworld')
        assert '\n' not in result
        assert 'hello' in result

    def test_extract_response(self):
        provider = AuggieProvider()
        output = '''Question text
● This is the response
More content
›'''
        result = provider.extract_response(output, 'Question text')
        assert result is not None
        assert 'This is the response' in result

    def test_get_skip_patterns(self):
        provider = AuggieProvider()
        skip = provider.get_skip_patterns()
        assert isinstance(skip, list)
        assert len(skip) > 0

    def test_get_activity_indicators(self):
        provider = AuggieProvider()
        indicators = provider.get_activity_indicators()
        assert 'Summarizing conversation history' in indicators or any('Summarizing' in i for i in indicators)


class TestCodexProvider:

    def test_provider_name(self):
        provider = CodexProvider()
        assert provider.name == 'codex'

    def test_config_values(self):
        provider = CodexProvider()
        assert provider.config.command == 'codex'
        assert provider.config.default_model is None
        assert 'gpt-5.1' in provider.config.supported_models

    def test_get_command_basic(self):
        provider = CodexProvider()
        cmd = provider.get_command('/home/user/project')
        assert any('codex' in c for c in cmd)

    def test_get_command_with_model(self):
        provider = CodexProvider()
        cmd = provider.get_command('/home/user/project', 'gpt-5.1')
        assert '--model' in cmd
        assert 'gpt-5.1' in cmd

    def test_get_prompt_patterns(self):
        provider = CodexProvider()
        patterns = provider.get_prompt_patterns()
        assert len(patterns) > 0
        assert any(p.search('›') or p.search('context left') for p in patterns)

    def test_get_response_markers(self):
        provider = CodexProvider()
        markers = provider.get_response_markers()
        assert len(markers) > 0
        assert '•' in markers

    def test_sanitize_message(self):
        provider = CodexProvider()
        result = provider.sanitize_message('hello\nworld')
        assert '\n' not in result
        spinner_chars = '⠋⠙⠹⠸⠼⠴'
        for char in spinner_chars:
            assert char not in provider.sanitize_message(f'test {char} message')

    def test_extract_response(self):
        provider = CodexProvider()
        output = '''Question text
• This is the response
More content
›'''
        result = provider.extract_response(output, 'Question text')
        assert result is not None
        assert 'This is the response' in result

    def test_get_skip_patterns(self):
        provider = CodexProvider()
        skip = provider.get_skip_patterns()
        assert isinstance(skip, list)
        assert 'Codex CLI' in skip

    def test_get_env_includes_nvm_path(self):
        provider = CodexProvider()
        env = provider.get_env()
        assert 'PATH' in env
        assert 'nvm' in env['PATH'] or '/usr' in env['PATH']


class TestProviderComparison:

    def test_providers_have_different_names(self):
        auggie = AuggieProvider()
        codex = CodexProvider()
        assert auggie.name != codex.name

    def test_providers_have_different_commands(self):
        auggie = AuggieProvider()
        codex = CodexProvider()
        assert auggie.config.command != codex.config.command

    def test_both_implement_required_methods(self):
        for provider in [AuggieProvider(), CodexProvider()]:
            assert hasattr(provider, 'get_command')
            assert hasattr(provider, 'get_prompt_patterns')
            assert hasattr(provider, 'get_end_patterns')
            assert hasattr(provider, 'get_response_markers')
            assert hasattr(provider, 'sanitize_message')
            assert hasattr(provider, 'extract_response')
            assert callable(provider.get_command)
            patterns = provider.get_prompt_patterns()
            assert len(patterns) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

