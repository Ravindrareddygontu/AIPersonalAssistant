"""Base provider abstraction for all AI modalities."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel


class ProviderCapability(str, Enum):
    """Capabilities that a provider can support."""
    
    CHAT = "chat"
    CHAT_STREAMING = "chat_streaming"
    VOICE_TO_TEXT = "voice_to_text"
    TEXT_TO_VOICE = "text_to_voice"
    VOICE_REALTIME = "voice_realtime"
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDIT = "image_edit"
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_GENERATION = "video_generation"
    VIDEO_ANALYSIS = "video_analysis"
    CODE_GENERATION = "code_generation"
    CODE_COMPLETION = "code_completion"
    CODE_ANALYSIS = "code_analysis"
    CODE_EXECUTION = "code_execution"


class ProviderInfo(BaseModel):
    """Information about a provider."""
    
    name: str
    display_name: str
    description: str
    capabilities: list[ProviderCapability]
    models: list[str]
    is_available: bool = True
    rate_limit: Optional[int] = None
    documentation_url: Optional[str] = None


class BaseProvider(ABC):
    """Abstract base class for all AI providers."""

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        self.api_key = api_key
        self.config = kwargs

    @property
    @abstractmethod
    def provider_info(self) -> ProviderInfo:
        """Return information about this provider."""
        ...

    @property
    def name(self) -> str:
        """Return the provider name."""
        return self.provider_info.name

    @property
    def capabilities(self) -> list[ProviderCapability]:
        """Return the provider's capabilities."""
        return self.provider_info.capabilities

    def supports(self, capability: ProviderCapability) -> bool:
        """Check if provider supports a capability."""
        return capability in self.capabilities

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy and accessible."""
        ...

    async def validate_api_key(self) -> bool:
        """Validate the API key is configured and valid."""
        return self.api_key is not None and len(self.api_key) > 0


class StreamingMixin:
    """Mixin for providers that support streaming responses."""

    async def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]:
        """Stream response chunks."""
        raise NotImplementedError("Streaming not implemented")
        yield  # Make this a generator

