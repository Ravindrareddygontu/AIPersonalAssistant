import logging
from typing import Dict, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.terminal_agent.base import TerminalAgentProvider

log = logging.getLogger('terminal_agent.registry')


class TerminalAgentRegistry:
    _providers: Dict[str, 'TerminalAgentProvider'] = {}
    _provider_classes: Dict[str, Type['TerminalAgentProvider']] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type['TerminalAgentProvider']) -> None:
        log.info(f"Registering terminal agent: {name}")
        cls._provider_classes[name] = provider_class

    @classmethod
    def get(cls, name: str) -> Optional['TerminalAgentProvider']:
        if name in cls._providers:
            return cls._providers[name]

        if name not in cls._provider_classes:
            log.warning(f"Terminal agent not found: {name}")
            return None

        try:
            provider = cls._provider_classes[name]()
            cls._providers[name] = provider
            return provider
        except Exception as e:
            log.exception(f"Failed to instantiate terminal agent {name}: {e}")
            return None

    @classmethod
    def list_providers(cls) -> list:
        return list(cls._provider_classes.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._provider_classes

    @classmethod
    def clear(cls) -> None:
        cls._providers.clear()
        cls._provider_classes.clear()

