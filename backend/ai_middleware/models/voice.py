from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class AudioFormat(str, Enum):

    MP3 = "mp3"
    WAV = "wav"
    WEBM = "webm"
    OGG = "ogg"
    FLAC = "flac"
    AAC = "aac"
    OPUS = "opus"
    PCM = "pcm"


class VoiceToTextRequest(BaseRequest):

    audio_data: bytes = Field(exclude=True)
    audio_format: AudioFormat = AudioFormat.WAV
    language: Optional[str] = None
    prompt: Optional[str] = None  # Optional context/prompt
    word_timestamps: bool = False
    response_format: str = "json"  # "json", "text", "srt", "vtt"


class WordTimestamp(BaseModel):

    word: str
    start: float
    end: float
    confidence: Optional[float] = None


class VoiceToTextResponse(BaseResponse):

    text: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    words: Optional[list[WordTimestamp]] = None
    confidence: Optional[float] = None
    segments: Optional[list[dict]] = None


class VoiceStyle(str, Enum):

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

    text: str
    voice: Optional[str] = None
    output_format: AudioFormat = AudioFormat.MP3
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=2.0)
    style: Optional[VoiceStyle] = None
    language: Optional[str] = None


class TextToVoiceResponse(BaseResponse):

    audio_data: bytes = Field(exclude=True)
    audio_format: AudioFormat
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    content_type: str = "audio/mpeg"

    class Config:
        arbitrary_types_allowed = True


class VoiceStreamChunk(StreamEvent):

    event_type: str = "voice.chunk"
    audio_chunk: bytes = Field(exclude=True)
    audio_format: AudioFormat
    duration_ms: Optional[float] = None
    
    class Config:
        arbitrary_types_allowed = True


class RealtimeVoiceConfig(BaseModel):

    voice: Optional[str] = None
    input_format: AudioFormat = AudioFormat.PCM
    output_format: AudioFormat = AudioFormat.PCM
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True  # Voice activity detection
    language: Optional[str] = None

