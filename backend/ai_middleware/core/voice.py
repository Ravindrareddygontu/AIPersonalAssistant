from abc import abstractmethod
from typing import Any, AsyncIterator, Optional

from backend.ai_middleware.core.base import BaseProvider, StreamingMixin
from backend.ai_middleware.models.voice import (
    TextToVoiceRequest,
    TextToVoiceResponse,
    VoiceToTextRequest,
    VoiceToTextResponse,
    VoiceStreamChunk,
)


class VoiceProvider(BaseProvider, StreamingMixin):

    @abstractmethod
    async def voice_to_text(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> VoiceToTextResponse:
        ...

    @abstractmethod
    async def text_to_voice(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        output_format: str = "mp3",
        speed: float = 1.0,
        **kwargs: Any,
    ) -> TextToVoiceResponse:
        ...

    async def text_to_voice_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[VoiceStreamChunk]:
        raise NotImplementedError("Streaming TTS not supported by this provider")
        yield  # Make this a generator

    async def voice_to_text_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        audio_format: str = "wav",
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[VoiceToTextResponse]:
        raise NotImplementedError("Streaming STT not supported by this provider")
        yield  # Make this a generator

    def create_tts_request(self, text: str, **kwargs: Any) -> TextToVoiceRequest:
        return TextToVoiceRequest(text=text, provider=self.name, **kwargs)

    def create_stt_request(
        self, audio_data: bytes, audio_format: str = "wav", **kwargs: Any
    ) -> VoiceToTextRequest:
        return VoiceToTextRequest(
            audio_data=audio_data,
            audio_format=audio_format,
            provider=self.name,
            **kwargs,
        )

