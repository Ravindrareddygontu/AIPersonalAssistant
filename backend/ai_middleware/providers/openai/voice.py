"""OpenAI Voice provider implementation (GPT-4o Transcribe + TTS)."""

import io
import time
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog

from backend.ai_middleware.config import get_settings
from backend.ai_middleware.core.base import ProviderCapability, ProviderInfo
from backend.ai_middleware.core.voice import VoiceProvider
from backend.ai_middleware.models.voice import (
    AudioFormat,
    TextToVoiceResponse,
    VoiceToTextResponse,
    WordTimestamp,
)
from backend.ai_middleware.providers.openai.base import OpenAIClientMixin
from backend.ai_middleware.middleware.error_handler import ProviderError

logger = structlog.get_logger()


class OpenAIVoiceProvider(VoiceProvider, OpenAIClientMixin):
    """OpenAI Voice provider using GPT-4o Transcribe (STT) and TTS API."""

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(api_key=api_key, **kwargs)
        self._settings = get_settings()

    @property
    def default_stt_model(self) -> str:
        """Get default STT model from config."""
        return self._settings.openai_stt_model

    @property
    def default_tts_model(self) -> str:
        """Get default TTS model from config."""
        return self._settings.openai_tts_model

    @property
    def default_voice(self) -> str:
        """Get default voice from config."""
        return self._settings.openai_tts_voice

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="openai-voice",
            display_name="OpenAI Voice",
            description="OpenAI GPT-4o Transcribe for speech-to-text and TTS for text-to-speech",
            capabilities=[
                ProviderCapability.VOICE_TO_TEXT,
                ProviderCapability.TEXT_TO_VOICE,
            ],
            models=[self.default_stt_model, self.default_tts_model],  # Dynamic from config
            documentation_url="https://platform.openai.com/docs/api-reference/audio",
        )

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            await self._make_request("GET", "/models", timeout=10.0)
            return True
        except Exception:
            return False

    async def voice_to_text(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> VoiceToTextResponse:
        """Transcribe audio using OpenAI Whisper."""
        start_time = time.perf_counter()
        request_id = uuid4()
        model = model or self.default_stt_model

        # Prepare the file for upload
        filename = f"audio.{audio_format}"
        files = {
            "file": (filename, io.BytesIO(audio_data), f"audio/{audio_format}"),
        }
        data = {
            "model": model,
            "response_format": kwargs.get("response_format", "json"),
        }
        
        if language:
            data["language"] = language
        if kwargs.get("prompt"):
            data["prompt"] = kwargs["prompt"]

        url = f"{self._get_base_url()}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self._get_api_key()}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                result = response.json()
            except httpx.HTTPStatusError as e:
                raise ProviderError(
                    message=f"OpenAI Whisper error: {e.response.text}",
                    provider="openai-voice",
                    original_error=e,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Parse word timestamps if available
        words = None
        if "words" in result:
            words = [
                WordTimestamp(
                    word=w["word"],
                    start=w["start"],
                    end=w["end"],
                )
                for w in result["words"]
            ]

        return VoiceToTextResponse(
            request_id=request_id,
            provider="openai-voice",
            model=model,
            created_at=datetime.utcnow(),
            text=result.get("text", ""),
            language=result.get("language"),
            duration_seconds=result.get("duration"),
            words=words,
            latency_ms=latency_ms,
        )

    async def text_to_voice(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        output_format: str = "mp3",
        speed: float = 1.0,
        **kwargs: Any,
    ) -> TextToVoiceResponse:
        """Convert text to speech using OpenAI TTS."""
        start_time = time.perf_counter()
        request_id = uuid4()

        model = model or self.default_tts_model
        voice = voice or self.default_voice

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": output_format,
            "speed": speed,
        }

        url = f"{self._get_base_url()}/audio/speech"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                audio_data = response.content
            except httpx.HTTPStatusError as e:
                raise ProviderError(
                    message=f"OpenAI TTS error: {e.response.text}",
                    provider="openai-voice",
                    original_error=e,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Map format to content type
        content_types = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm",
        }

        return TextToVoiceResponse(
            request_id=request_id,
            provider="openai-voice",
            model=model,
            created_at=datetime.utcnow(),
            audio_data=audio_data,
            audio_format=AudioFormat(output_format),
            content_type=content_types.get(output_format, "audio/mpeg"),
            latency_ms=latency_ms,
        )

