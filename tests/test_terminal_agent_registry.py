import pytest
import sys
import os
import re
from typing import List, Optional, Pattern

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.terminal_agent.base import TerminalAgentConfig, TerminalAgentProvider
from backend.services.terminal_agent.registry import TerminalAgentRegistry


class MockRegistryProvider(TerminalAgentProvider):

    def __init__(self, name: str = 'test'):
        config = TerminalAgentConfig(name=name, command=f'{name}-cmd')
        super().__init__(config)

    def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
        return [self.config.command]

    def get_prompt_patterns(self) -> List[Pattern]:
        return [re.compile(r'>\s*$')]

    def get_end_patterns(self) -> List[Pattern]:
        return [re.compile(r'Done')]

    def get_response_markers(self) -> List[str]:
        return ['●']

    def get_activity_indicators(self) -> List[str]:
        return ['Processing...']

    def get_skip_patterns(self) -> List[str]:
        return []

    def sanitize_message(self, message: str) -> str:
        return message

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        return raw_output


class TestTerminalAgentRegistry:

    def setup_method(self):
        TerminalAgentRegistry._providers.clear()
        TerminalAgentRegistry._provider_classes.clear()

    def teardown_method(self):
        TerminalAgentRegistry._providers.clear()
        TerminalAgentRegistry._provider_classes.clear()

    def test_register_provider(self):
        TerminalAgentRegistry.register('test1', MockRegistryProvider)
        assert TerminalAgentRegistry.is_registered('test1')

    def test_get_provider(self):
        TerminalAgentRegistry.register('test2', MockRegistryProvider)
        provider = TerminalAgentRegistry.get('test2')
        assert provider is not None
        assert provider.name == 'test'  # Provider uses its internal name from config

    def test_get_unregistered_returns_none(self):
        provider = TerminalAgentRegistry.get('nonexistent')
        assert provider is None

    def test_list_providers(self):
        TerminalAgentRegistry.register('provider_a', MockRegistryProvider)
        TerminalAgentRegistry.register('provider_b', MockRegistryProvider)
        providers = TerminalAgentRegistry.list_providers()
        assert 'provider_a' in providers
        assert 'provider_b' in providers
        assert len(providers) == 2

    def test_is_registered_true(self):
        TerminalAgentRegistry.register('registered', MockRegistryProvider)
        assert TerminalAgentRegistry.is_registered('registered') is True

    def test_is_registered_false(self):
        assert TerminalAgentRegistry.is_registered('not_registered') is False

    def test_register_overwrites(self):
        class AnotherProvider(MockRegistryProvider):
            def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
                return ['another-cmd']

        TerminalAgentRegistry.register('overwrite', MockRegistryProvider)
        TerminalAgentRegistry.register('overwrite', AnotherProvider)
        provider = TerminalAgentRegistry.get('overwrite')
        cmd = provider.get_command('/tmp')
        assert cmd == ['another-cmd']

    def test_provider_instances_are_cached(self):
        TerminalAgentRegistry.register('cached', MockRegistryProvider)
        provider1 = TerminalAgentRegistry.get('cached')
        provider2 = TerminalAgentRegistry.get('cached')
        assert provider1 is provider2

    def test_multiple_providers_isolated(self):
        class ProviderA(MockRegistryProvider):
            def __init__(self, name: str = 'a'):
                super().__init__(name)

        class ProviderB(MockRegistryProvider):
            def __init__(self, name: str = 'b'):
                super().__init__(name)

        TerminalAgentRegistry.register('a', ProviderA)
        TerminalAgentRegistry.register('b', ProviderB)

        provider_a = TerminalAgentRegistry.get('a')
        provider_b = TerminalAgentRegistry.get('b')

        assert provider_a.name == 'a'
        assert provider_b.name == 'b'
        assert provider_a is not provider_b


class TestRegistryIntegration:

    def setup_method(self):
        TerminalAgentRegistry._providers.clear()
        TerminalAgentRegistry._provider_classes.clear()

    def teardown_method(self):
        TerminalAgentRegistry._providers.clear()
        TerminalAgentRegistry._provider_classes.clear()

    def test_register_auggie_provider(self):
        from backend.services.auggie import register_auggie_provider
        register_auggie_provider()
        assert TerminalAgentRegistry.is_registered('auggie')
        provider = TerminalAgentRegistry.get('auggie')
        assert provider.name == 'auggie'

    def test_register_codex_provider(self):
        from backend.services.codex import register_codex_provider
        register_codex_provider()
        assert TerminalAgentRegistry.is_registered('codex')
        provider = TerminalAgentRegistry.get('codex')
        assert provider.name == 'codex'

    def test_register_both_providers(self):
        from backend.services.auggie import register_auggie_provider
        from backend.services.codex import register_codex_provider
        register_auggie_provider()
        register_codex_provider()
        providers = TerminalAgentRegistry.list_providers()
        assert 'auggie' in providers
        assert 'codex' in providers


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

