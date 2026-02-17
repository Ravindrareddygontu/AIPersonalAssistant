"""OpenAI Image provider implementation (GPT Image / DALL-E)."""

import base64
import io
import time
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog

from backend.ai_middleware.config import get_settings
from backend.ai_middleware.core.base import ProviderCapability, ProviderInfo
from backend.ai_middleware.core.image import ImageProvider
from backend.ai_middleware.models.image import (
    GeneratedImage,
    ImageAnalysisResponse,
    ImageEditResponse,
    ImageGenerationResponse,
)
from backend.ai_middleware.providers.openai.base import OpenAIClientMixin
from backend.ai_middleware.middleware.error_handler import ProviderError

logger = structlog.get_logger()


class OpenAIImageProvider(ImageProvider, OpenAIClientMixin):
    """OpenAI Image provider using GPT Image and DALL-E models."""

    VALID_SIZES_GPT_IMAGE = ["1024x1024", "1536x1024", "1024x1536", "auto"]
    VALID_SIZES_DALLE3 = ["1024x1024", "1792x1024", "1024x1792"]
    VALID_SIZES_DALLE2 = ["256x256", "512x512", "1024x1024"]

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(api_key=api_key, **kwargs)
        self._settings = get_settings()

    @property
    def default_model(self) -> str:
        """Get default model from config."""
        return self._settings.openai_image_model

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="openai-image",
            display_name="OpenAI Image",
            description="OpenAI GPT Image and DALL-E models for image generation and editing",
            capabilities=[
                ProviderCapability.IMAGE_GENERATION,
                ProviderCapability.IMAGE_EDIT,
            ],
            models=[self.default_model],  # Dynamic from config
            documentation_url="https://platform.openai.com/docs/api-reference/images",
        )

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            await self._make_request("GET", "/models", timeout=10.0)
            return True
        except Exception:
            return False

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """Generate images using DALL-E."""
        start_time = time.perf_counter()
        request_id = uuid4()
        model = model or self.default_model

        # Validate size based on model
        if model == "dall-e-3":
            if size not in self.VALID_SIZES_DALLE3:
                size = "1024x1024"
            # DALL-E 3 only supports n=1
            n = 1
        else:
            if size not in self.VALID_SIZES_DALLE2:
                size = "1024x1024"

        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": kwargs.get("response_format", "url"),
        }
        
        if model == "dall-e-3":
            payload["quality"] = quality
            if kwargs.get("style"):
                payload["style"] = kwargs["style"]

        response = await self._make_request(
            "POST", "/images/generations", payload, timeout=120.0
        )
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        images = [
            GeneratedImage(
                url=img.get("url"),
                b64_data=img.get("b64_json"),
                revised_prompt=img.get("revised_prompt"),
            )
            for img in response["data"]
        ]

        return ImageGenerationResponse(
            request_id=request_id,
            provider="openai-image",
            model=model,
            created_at=datetime.utcnow(),
            images=images,
            latency_ms=latency_ms,
        )

    async def edit_image(
        self,
        image_data: bytes,
        prompt: str,
        mask_data: Optional[bytes] = None,
        model: Optional[str] = None,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageEditResponse:
        """Edit an image using DALL-E 2."""
        start_time = time.perf_counter()
        request_id = uuid4()
        
        # DALL-E 2 only supports image editing
        model = "dall-e-2"
        
        url = f"{self._get_base_url()}/images/edits"
        headers = {"Authorization": f"Bearer {self._get_api_key()}"}
        
        files = {
            "image": ("image.png", io.BytesIO(image_data), "image/png"),
        }
        if mask_data:
            files["mask"] = ("mask.png", io.BytesIO(mask_data), "image/png")
        
        data = {
            "prompt": prompt,
            "size": size,
            "n": kwargs.get("n", 1),
            "response_format": kwargs.get("response_format", "url"),
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
            except httpx.HTTPStatusError as e:
                raise ProviderError(
                    message=f"OpenAI image edit error: {e.response.text}",
                    provider="openai-image",
                    original_error=e,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        
        images = [
            GeneratedImage(url=img.get("url"), b64_data=img.get("b64_json"))
            for img in result["data"]
        ]

        return ImageEditResponse(
            request_id=request_id,
            provider="openai-image",
            model=model,
            created_at=datetime.utcnow(),
            images=images,
            latency_ms=latency_ms,
        )

    async def create_variation(
        self,
        image_data: bytes,
        n: int = 1,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageGenerationResponse:
        """Create variations of an image using DALL-E 2."""
        start_time = time.perf_counter()
        request_id = uuid4()
        model = "dall-e-2"
        
        url = f"{self._get_base_url()}/images/variations"
        headers = {"Authorization": f"Bearer {self._get_api_key()}"}
        
        files = {"image": ("image.png", io.BytesIO(image_data), "image/png")}
        data = {"n": n, "size": size, "response_format": kwargs.get("response_format", "url")}

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
            except httpx.HTTPStatusError as e:
                raise ProviderError(
                    message=f"OpenAI variation error: {e.response.text}",
                    provider="openai-image",
                    original_error=e,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        images = [GeneratedImage(url=img.get("url"), b64_data=img.get("b64_json")) for img in result["data"]]

        return ImageGenerationResponse(
            request_id=request_id, provider="openai-image", model=model,
            created_at=datetime.utcnow(), images=images, latency_ms=latency_ms,
        )

