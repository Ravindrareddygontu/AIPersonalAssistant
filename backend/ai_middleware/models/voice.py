"""Voice/speech models."""

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class AudioFormat(str, Enum):
    """Supported audio formats."""

    MP3 = "mp3"
    WAV = "wav"
    WEBM = "webm"
    OGG = "ogg"
    FLAC = "flac"
    AAC = "aac"
    OPUS = "opus"
    PCM = "pcm"


class VoiceToTextRequest(BaseRequest):
    """Speech-to-text request."""

    audio_data: bytes = Field(exclude=True)  # Exclude from JSON serialization
    audio_format: AudioFormat = AudioFormat.WAV
    language: Optional[str] = None
    prompt: Optional[str] = None  # Optional context/prompt
    word_timestamps: bool = False
    response_format: str = "json"  # "json", "text", "srt", "vtt"


class WordTimestamp(BaseModel):
    """Timestamp information for a word."""

    word: str
    start: float
    end: float
    confidence: Optional[float] = None


class VoiceToTextResponse(BaseResponse):
    """Speech-to-text response."""

    text: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    words: Optional[list[WordTimestamp]] = None
    confidence: Optional[float] = None
    segments: Optional[list[dict]] = None


class VoiceStyle(str, Enum):
    """Voice speaking styles."""

    NEUTRAL = "neutral"
    CHEERFUL = "cheerful"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    DISGUST = "disgust"
    SURPRISED = "surprised"
    CALM = "calm"
    SERIOUS = "serious"


class TextToVoiceRequest(BaseRequest):
    """Text-to-speech request."""

    text: str
    voice: Optional[str] = None
    output_format: AudioFormat = AudioFormat.MP3
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=2.0)
    style: Optional[VoiceStyle] = None
    language: Optional[str] = None


class TextToVoiceResponse(BaseResponse):
    """Text-to-speech response."""

    audio_data: bytes = Field(exclude=True)
    audio_format: AudioFormat
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    content_type: str = "audio/mpeg"

    class Config:
        arbitrary_types_allowed = True


class VoiceStreamChunk(StreamEvent):
    """A chunk of streaming audio data."""

    event_type: str = "voice.chunk"
    audio_chunk: bytes = Field(exclude=True)
    audio_format: AudioFormat
    duration_ms: Optional[float] = None
    
    class Config:
        arbitrary_types_allowed = True


class RealtimeVoiceConfig(BaseModel):
    """Configuration for real-time voice sessions."""

    voice: Optional[str] = None
    input_format: AudioFormat = AudioFormat.PCM
    output_format: AudioFormat = AudioFormat.PCM
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True  # Voice activity detection
    language: Optional[str] = None

