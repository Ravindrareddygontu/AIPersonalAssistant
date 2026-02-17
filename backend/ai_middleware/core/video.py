"""Video provider abstraction."""

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
    """Abstract base class for video AI providers."""

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
        """
        Generate a video from a text prompt.

        Args:
            prompt: Text description of the video to generate
            model: Model to use (provider-specific)
            duration: Video duration in seconds
            resolution: Video resolution (e.g., "720p", "1080p", "4k")
            fps: Frames per second
            **kwargs: Additional provider-specific parameters

        Returns:
            VideoGenerationResponse with generated video
        """
        ...

    async def generate_video_from_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        duration: float = 5.0,
        **kwargs: Any,
    ) -> VideoGenerationResponse:
        """
        Generate a video from an image (image-to-video).

        Args:
            image_data: Starting image bytes
            prompt: Optional motion/action description
            model: Model to use
            duration: Video duration in seconds
            **kwargs: Additional parameters

        Returns:
            VideoGenerationResponse with generated video
        """
        raise NotImplementedError("Image-to-video not supported by this provider")

    async def analyze_video(
        self,
        video_data: bytes,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        timestamps: bool = False,
        **kwargs: Any,
    ) -> VideoAnalysisResponse:
        """
        Analyze a video and describe its contents.

        Args:
            video_data: Video bytes to analyze
            prompt: Optional question about the video
            model: Model to use
            timestamps: Include timestamps in analysis
            **kwargs: Additional parameters

        Returns:
            VideoAnalysisResponse with analysis
        """
        raise NotImplementedError("Video analysis not supported by this provider")

    async def analyze_video_stream(
        self,
        video_stream: AsyncIterator[bytes],
        prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[VideoAnalysisResponse]:
        """
        Analyze a video stream in real-time.

        Args:
            video_stream: Async iterator of video frames/chunks
            prompt: Optional context for analysis
            **kwargs: Additional parameters

        Yields:
            VideoAnalysisResponse objects for each segment
        """
        raise NotImplementedError("Video stream analysis not supported")
        yield  # Make this a generator

    async def stream_video_generation(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[VideoStreamChunk]:
        """
        Stream video generation progress/chunks.

        Args:
            prompt: Text description of video
            **kwargs: Additional parameters

        Yields:
            VideoStreamChunk objects as video generates
        """
        raise NotImplementedError("Streaming video generation not supported")
        yield  # Make this a generator

    def create_generation_request(
        self, prompt: str, **kwargs: Any
    ) -> VideoGenerationRequest:
        """Create a VideoGenerationRequest object."""
        return VideoGenerationRequest(prompt=prompt, provider=self.name, **kwargs)

    def create_analysis_request(
        self, video_data: bytes, **kwargs: Any
    ) -> VideoAnalysisRequest:
        """Create a VideoAnalysisRequest object."""
        return VideoAnalysisRequest(
            video_data=video_data, provider=self.name, **kwargs
        )

