from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from backend.ai_middleware.api.dependencies import ApiKeyDep, ProviderDep, RegistryDep
from backend.ai_middleware.models.image import (
    ImageAnalysisResponse,
    ImageEditResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)

router = APIRouter()


@router.post("/generate", response_model=ImageGenerationResponse)
async def generate_image(
    request: ImageGenerationRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> ImageGenerationResponse:
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    image_provider = registry.get_image_provider(provider_name)
    
    response = await image_provider.generate_image(
        prompt=request.prompt,
        model=request.model,
        size=request.size,
        quality=request.quality.value,
        n=request.n,
        style=request.style.value if request.style else None,
    )
    
    return response


@router.post("/edit", response_model=ImageEditResponse)
async def edit_image(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    image: UploadFile = File(...),
    prompt: str = Form(...),
    mask: Optional[UploadFile] = File(None),
    size: str = Form("1024x1024"),
    n: int = Form(1),
) -> ImageEditResponse:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    image_provider = registry.get_image_provider(provider)
    
    image_data = await image.read()
    mask_data = await mask.read() if mask else None
    
    response = await image_provider.edit_image(
        image_data=image_data,
        prompt=prompt,
        mask_data=mask_data,
        size=size,
        n=n,
    )
    
    return response


@router.post("/analyze", response_model=ImageAnalysisResponse)
async def analyze_image(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    detail: str = Form("auto"),
) -> ImageAnalysisResponse:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    image_provider = registry.get_image_provider(provider)
    
    image_data = await image.read()
    
    response = await image_provider.analyze_image(
        image_data=image_data,
        prompt=prompt,
    )
    
    return response


@router.post("/variations", response_model=ImageGenerationResponse)
async def create_image_variations(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    image: UploadFile = File(...),
    n: int = Form(1),
    size: str = Form("1024x1024"),
) -> ImageGenerationResponse:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    image_provider = registry.get_image_provider(provider)
    
    image_data = await image.read()
    
    response = await image_provider.create_variation(
        image_data=image_data,
        n=n,
        size=size,
    )
    
    return response

