# Auggie execution services
from .executor import AuggieExecutor, AuggieResponse
from .summarizer import ResponseSummarizer
from .provider import AuggieProvider

__all__ = ['AuggieExecutor', 'AuggieResponse', 'ResponseSummarizer', 'AuggieProvider']


def register_auggie_provider():
    from backend.services.terminal_agent.registry import TerminalAgentRegistry
    TerminalAgentRegistry.register('auggie', AuggieProvider)

