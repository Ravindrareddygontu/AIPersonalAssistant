from functools import lru_cache
from typing import Any, Dict, List, Optional, Type, TypeVar

import structlog

from backend.ai_middleware.core.base import BaseProvider, ProviderCapability, ProviderInfo
from backend.ai_middleware.core.chat import ChatProvider
from backend.ai_middleware.core.code import CodeProvider
from backend.ai_middleware.core.image import ImageProvider
from backend.ai_middleware.core.video import VideoProvider
from backend.ai_middleware.core.voice import VoiceProvider

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseProvider)


class ProviderNotFoundError(Exception):
    pass


class ProviderRegistry:

    def __init__(self) -> None:
        self._providers: Dict[str, Type[BaseProvider]] = {}
        self._instances: Dict[str, BaseProvider] = {}
        self._provider_configs: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        provider_class: Type[T],
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Create temporary instance to get provider info
        temp_instance = provider_class(**(config or {}))
        name = temp_instance.provider_info.name
        
        self._providers[name] = provider_class
        self._provider_configs[name] = config or {}
        
        logger.info(
            "Provider registered",
            provider=name,
            capabilities=[c.value for c in temp_instance.capabilities],
        )

    def unregister(self, name: str) -> None:
        if name in self._providers:
            del self._providers[name]
            self._instances.pop(name, None)
            self._provider_configs.pop(name, None)
            logger.info("Provider unregistered", provider=name)

    def get(self, name: str, **kwargs: Any) -> BaseProvider:
        if name not in self._providers:
            raise ProviderNotFoundError(f"Provider '{name}' not found")
        
        # Merge registered config with runtime kwargs
        config = {**self._provider_configs.get(name, {}), **kwargs}
        
        # Create new instance if not cached or if new kwargs provided
        cache_key = f"{name}:{hash(frozenset(config.items()))}"
        if cache_key not in self._instances:
            self._instances[cache_key] = self._providers[name](**config)
        
        return self._instances[cache_key]

    def get_chat_provider(self, name: str, **kwargs: Any) -> ChatProvider:
        provider = self.get(name, **kwargs)
        if not isinstance(provider, ChatProvider):
            raise TypeError(f"Provider '{name}' is not a ChatProvider")
        return provider

    def get_voice_provider(self, name: str, **kwargs: Any) -> VoiceProvider:
        provider = self.get(name, **kwargs)
        if not isinstance(provider, VoiceProvider):
            raise TypeError(f"Provider '{name}' is not a VoiceProvider")
        return provider

    def get_image_provider(self, name: str, **kwargs: Any) -> ImageProvider:
        provider = self.get(name, **kwargs)
        if not isinstance(provider, ImageProvider):
            raise TypeError(f"Provider '{name}' is not an ImageProvider")
        return provider

    def get_video_provider(self, name: str, **kwargs: Any) -> VideoProvider:
        provider = self.get(name, **kwargs)
        if not isinstance(provider, VideoProvider):
            raise TypeError(f"Provider '{name}' is not a VideoProvider")
        return provider

    def get_code_provider(self, name: str, **kwargs: Any) -> CodeProvider:
        provider = self.get(name, **kwargs)
        if not isinstance(provider, CodeProvider):
            raise TypeError(f"Provider '{name}' is not a CodeProvider")
        return provider

    def list_providers(self) -> List[ProviderInfo]:
        return [
            self._providers[name](**self._provider_configs.get(name, {})).provider_info
            for name in self._providers
        ]

    def find_by_capability(
        self, capability: ProviderCapability
    ) -> List[ProviderInfo]:
        return [
            info for info in self.list_providers()
            if capability in info.capabilities
        ]

    def has_provider(self, name: str) -> bool:
        return name in self._providers


# Global registry instance
_registry: Optional[ProviderRegistry] = None


@lru_cache
def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def register_provider(
    provider_class: Type[BaseProvider],
    config: Optional[Dict[str, Any]] = None,
) -> None:
    get_registry().register(provider_class, config)

