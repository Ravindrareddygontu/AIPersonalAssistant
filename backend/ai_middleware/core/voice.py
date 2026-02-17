"""Voice provider abstraction."""

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
    """Abstract base class for voice/speech AI providers."""

    @abstractmethod
    async def voice_to_text(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> VoiceToTextResponse:
        """
        Transcribe audio to text (Speech-to-Text).

        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format (wav, mp3, webm, etc.)
            language: Language code (e.g., "en", "es")
            model: Model to use (provider-specific)
            **kwargs: Additional provider-specific parameters

        Returns:
            VoiceToTextResponse with transcription
        """
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
        """
        Convert text to speech (Text-to-Speech).

        Args:
            text: Text to convert to speech
            voice: Voice ID to use
            model: Model to use (provider-specific)
            output_format: Output audio format
            speed: Speech speed multiplier
            **kwargs: Additional provider-specific parameters

        Returns:
            TextToVoiceResponse with audio data
        """
        ...

    async def text_to_voice_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[VoiceStreamChunk]:
        """
        Stream text-to-speech audio chunks.

        Args:
            text: Text to convert to speech
            voice: Voice ID to use
            model: Model to use
            **kwargs: Additional parameters

        Yields:
            VoiceStreamChunk objects with audio data
        """
        raise NotImplementedError("Streaming TTS not supported by this provider")
        yield  # Make this a generator

    async def voice_to_text_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        audio_format: str = "wav",
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[VoiceToTextResponse]:
        """
        Stream transcription from audio stream.

        Args:
            audio_stream: Async iterator of audio chunks
            audio_format: Audio format
            language: Language code
            **kwargs: Additional parameters

        Yields:
            VoiceToTextResponse objects with partial transcriptions
        """
        raise NotImplementedError("Streaming STT not supported by this provider")
        yield  # Make this a generator

    def create_tts_request(self, text: str, **kwargs: Any) -> TextToVoiceRequest:
        """Create a TextToVoiceRequest object."""
        return TextToVoiceRequest(text=text, provider=self.name, **kwargs)

    def create_stt_request(
        self, audio_data: bytes, audio_format: str = "wav", **kwargs: Any
    ) -> VoiceToTextRequest:
        """Create a VoiceToTextRequest object."""
        return VoiceToTextRequest(
            audio_data=audio_data,
            audio_format=audio_format,
            provider=self.name,
            **kwargs,
        )

