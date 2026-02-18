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
        raise NotImplementedError("Image editing not supported by this provider")

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ImageAnalysisResponse:
        raise NotImplementedError("Image analysis not supported by this provider")

    async def create_variation(
        self,
        image_data: bytes,
        n: int = 1,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        raise NotImplementedError("Image variations not supported by this provider")

    def create_generation_request(
        self, prompt: str, **kwargs: Any
    ) -> ImageGenerationRequest:
        return ImageGenerationRequest(prompt=prompt, provider=self.name, **kwargs)

    def create_edit_request(
        self, image_data: bytes, prompt: str, **kwargs: Any
    ) -> ImageEditRequest:
        return ImageEditRequest(
            image_data=image_data, prompt=prompt, provider=self.name, **kwargs
        )

    def create_analysis_request(
        self, image_data: bytes, **kwargs: Any
    ) -> ImageAnalysisRequest:
        return ImageAnalysisRequest(
            image_data=image_data, provider=self.name, **kwargs
        )

