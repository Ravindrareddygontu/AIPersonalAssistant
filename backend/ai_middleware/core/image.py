"""Image provider abstraction."""

from abc import abstractmethod
from typing import Any, Optional

from backend.ai_middleware.core.base import BaseProvider
from backend.ai_middleware.models.image import (
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    ImageEditRequest,
    ImageEditResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)


class ImageProvider(BaseProvider):
    """Abstract base class for image AI providers."""

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """
        Generate images from a text prompt.

        Args:
            prompt: Text description of the image to generate
            model: Model to use (provider-specific)
            size: Image size (e.g., "1024x1024", "512x512")
            quality: Image quality ("standard", "hd")
            n: Number of images to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            ImageGenerationResponse with generated image(s)
        """
        ...

    async def edit_image(
        self,
        image_data: bytes,
        prompt: str,
        mask_data: Optional[bytes] = None,
        model: Optional[str] = None,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageEditResponse:
        """
        Edit an existing image based on a prompt.

        Args:
            image_data: Original image bytes
            prompt: Description of the edit to make
            mask_data: Optional mask indicating areas to edit
            model: Model to use
            size: Output image size
            **kwargs: Additional parameters

        Returns:
            ImageEditResponse with edited image
        """
        raise NotImplementedError("Image editing not supported by this provider")

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ImageAnalysisResponse:
        """
        Analyze an image and describe its contents.

        Args:
            image_data: Image bytes to analyze
            prompt: Optional question about the image
            model: Model to use
            **kwargs: Additional parameters

        Returns:
            ImageAnalysisResponse with analysis
        """
        raise NotImplementedError("Image analysis not supported by this provider")

    async def create_variation(
        self,
        image_data: bytes,
        n: int = 1,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """
        Create variations of an existing image.

        Args:
            image_data: Original image bytes
            n: Number of variations to generate
            size: Output image size
            **kwargs: Additional parameters

        Returns:
            ImageGenerationResponse with variations
        """
        raise NotImplementedError("Image variations not supported by this provider")

    def create_generation_request(
        self, prompt: str, **kwargs: Any
    ) -> ImageGenerationRequest:
        """Create an ImageGenerationRequest object."""
        return ImageGenerationRequest(prompt=prompt, provider=self.name, **kwargs)

    def create_edit_request(
        self, image_data: bytes, prompt: str, **kwargs: Any
    ) -> ImageEditRequest:
        """Create an ImageEditRequest object."""
        return ImageEditRequest(
            image_data=image_data, prompt=prompt, provider=self.name, **kwargs
        )

    def create_analysis_request(
        self, image_data: bytes, **kwargs: Any
    ) -> ImageAnalysisRequest:
        """Create an ImageAnalysisRequest object."""
        return ImageAnalysisRequest(
            image_data=image_data, provider=self.name, **kwargs
        )

