from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse


class ImageSize(str, Enum):

    SMALL = "256x256"
    MEDIUM = "512x512"
    LARGE = "1024x1024"
    WIDE = "1792x1024"
    TALL = "1024x1792"


class ImageQuality(str, Enum):

    STANDARD = "standard"
    HD = "hd"


class ImageStyle(str, Enum):

    NATURAL = "natural"
    VIVID = "vivid"
    ARTISTIC = "artistic"
    PHOTOGRAPHIC = "photographic"


class ImageGenerationRequest(BaseRequest):

    prompt: str
    negative_prompt: Optional[str] = None
    size: str = "1024x1024"
    quality: ImageQuality = ImageQuality.STANDARD
    style: Optional[ImageStyle] = None
    n: int = Field(default=1, ge=1, le=10)
    seed: Optional[int] = None
    guidance_scale: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    steps: Optional[int] = Field(default=None, ge=1, le=150)


class GeneratedImage(BaseModel):

    url: Optional[str] = None
    b64_data: Optional[str] = None
    revised_prompt: Optional[str] = None
    seed: Optional[int] = None


class ImageGenerationResponse(BaseResponse):

    images: list[GeneratedImage]

    @property
    def first_image(self) -> Optional[GeneratedImage]:
        return self.images[0] if self.images else None


class ImageEditRequest(BaseRequest):

    image_data: bytes = Field(exclude=True)
    prompt: str
    mask_data: Optional[bytes] = Field(default=None, exclude=True)
    size: str = "1024x1024"
    n: int = Field(default=1, ge=1, le=10)


class ImageEditResponse(BaseResponse):

    images: list[GeneratedImage]


class ImageAnalysisRequest(BaseRequest):

    image_data: bytes = Field(exclude=True)
    image_url: Optional[str] = None
    prompt: Optional[str] = None
    detail: str = "auto"  # "low", "high", "auto"
    max_tokens: Optional[int] = None


class BoundingBox(BaseModel):

    x: float
    y: float
    width: float
    height: float


class DetectedObject(BaseModel):

    label: str
    confidence: float
    bounding_box: Optional[BoundingBox] = None


class ImageAnalysisResponse(BaseResponse):

    description: str
    objects: Optional[list[DetectedObject]] = None
    tags: Optional[list[str]] = None
    text_content: Optional[list[str]] = None  # OCR results
    is_nsfw: Optional[bool] = None
    colors: Optional[list[str]] = None
    faces: Optional[int] = None

