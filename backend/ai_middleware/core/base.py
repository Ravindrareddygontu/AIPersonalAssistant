from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel


class ProviderCapability(str, Enum):
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
    name: str
    display_name: str
    description: str
    capabilities: list[ProviderCapability]
    models: list[str]
    is_available: bool = True
    rate_limit: Optional[int] = None
    documentation_url: Optional[str] = None


class BaseProvider(ABC):

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        self.api_key = api_key
        self.config = kwargs

    @property
    @abstractmethod
    def provider_info(self) -> ProviderInfo:
        ...

    @property
    def name(self) -> str:
        return self.provider_info.name

    @property
    def capabilities(self) -> list[ProviderCapability]:
        return self.provider_info.capabilities

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    async def validate_api_key(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 0


class StreamingMixin:

    async def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError("Streaming not implemented")
        yield  # Make this a generator

