# Codex CLI integration services
from .provider import CodexProvider

__all__ = ['CodexProvider']


def register_codex_provider():
    from backend.services.terminal_agent.registry import TerminalAgentRegistry
    TerminalAgentRegistry.register('codex', CodexProvider)

