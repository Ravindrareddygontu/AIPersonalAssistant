from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class VideoResolution(str, Enum):

    SD_480P = "480p"
    HD_720P = "720p"
    FHD_1080P = "1080p"
    QHD_1440P = "1440p"
    UHD_4K = "4k"


class VideoFormat(str, Enum):

    MP4 = "mp4"
    WEBM = "webm"
    MOV = "mov"
    GIF = "gif"


class VideoGenerationRequest(BaseRequest):

    prompt: str
    negative_prompt: Optional[str] = None
    duration: float = Field(default=5.0, ge=1.0, le=60.0)
    resolution: VideoResolution = VideoResolution.FHD_1080P
    fps: int = Field(default=24, ge=1, le=60)
    output_format: VideoFormat = VideoFormat.MP4
    seed: Optional[int] = None
    aspect_ratio: Optional[str] = None  # "16:9", "9:16", "1:1"
    start_image: Optional[bytes] = Field(default=None, exclude=True)
    end_image: Optional[bytes] = Field(default=None, exclude=True)


class GeneratedVideo(BaseModel):

    url: Optional[str] = None
    b64_data: Optional[str] = None
    duration_seconds: float
    resolution: str
    fps: int
    format: VideoFormat
    thumbnail_url: Optional[str] = None
    seed: Optional[int] = None


class VideoGenerationResponse(BaseResponse):

    video: GeneratedVideo
    generation_time_seconds: Optional[float] = None


class VideoAnalysisRequest(BaseRequest):

    video_data: bytes = Field(exclude=True)
    video_url: Optional[str] = None
    prompt: Optional[str] = None
    include_timestamps: bool = False
    include_audio_transcript: bool = False
    frame_interval: Optional[float] = None  # Seconds between analyzed frames


class VideoSegment(BaseModel):

    start_time: float
    end_time: float
    description: str
    confidence: Optional[float] = None
    labels: Optional[list[str]] = None


class VideoAnalysisResponse(BaseResponse):

    description: str
    duration_seconds: float
    segments: Optional[list[VideoSegment]] = None
    transcript: Optional[str] = None
    detected_objects: Optional[list[str]] = None
    detected_activities: Optional[list[str]] = None
    is_nsfw: Optional[bool] = None
    frame_count: Optional[int] = None


class VideoStreamChunk(StreamEvent):

    event_type: str = "video.chunk"
    progress_percent: float
    preview_url: Optional[str] = None
    status: str  # "processing", "rendering", "complete"
    estimated_time_remaining: Optional[float] = None

