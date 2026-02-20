from abc import abstractmethod
from typing import Any, AsyncIterator, Optional

from backend.ai_middleware.core.base import BaseProvider, StreamingMixin
from backend.ai_middleware.models.video import (
    VideoAnalysisRequest,
    VideoAnalysisResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStreamChunk,
)


class VideoProvider(BaseProvider, StreamingMixin):

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        model: Optional[str] = None,
        duration: float = 5.0,
        resolution: str = "1080p",
        fps: int = 24,
        **kwargs: Any,
    ) -> VideoGenerationResponse:
        ...

    async def generate_video_from_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        duration: float = 5.0,
        **kwargs: Any,
    ) -> VideoGenerationResponse:
        raise NotImplementedError("Image-to-video not supported by this provider")

    async def analyze_video(
        self,
        _video_data: bytes,
        _prompt: Optional[str] = None,
        _model: Optional[str] = None,
        _timestamps: bool = False,
        **_kwargs: Any,
    ) -> VideoAnalysisResponse:
        raise NotImplementedError("Video analysis not supported by this provider")

    async def analyze_video_stream(
        self,
        _video_stream: AsyncIterator[bytes],
        _prompt: Optional[str] = None,
        **_kwargs: Any,
    ) -> AsyncIterator[VideoAnalysisResponse]:
        raise NotImplementedError("Video stream analysis not supported")
        yield  # Make this a generator

    async def stream_video_generation(
        self,
        _prompt: str,
        **_kwargs: Any,
    ) -> AsyncIterator[VideoStreamChunk]:
        raise NotImplementedError("Streaming video generation not supported")
        yield  # Make this a generator

    def create_generation_request(
        self, prompt: str, **kwargs: Any
    ) -> VideoGenerationRequest:
        return VideoGenerationRequest(prompt=prompt, provider=self.name, **kwargs)

    def create_analysis_request(
        self, video_data: bytes, **kwargs: Any
    ) -> VideoAnalysisRequest:
        return VideoAnalysisRequest(
            video_data=video_data, provider=self.name, **kwargs
        )

