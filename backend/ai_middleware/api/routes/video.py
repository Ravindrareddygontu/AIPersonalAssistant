from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from backend.ai_middleware.api.dependencies import ApiKeyDep, ProviderDep, RegistryDep
from backend.ai_middleware.models.video import (
    VideoAnalysisResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
)

router = APIRouter()


@router.post("/generate", response_model=VideoGenerationResponse)
async def generate_video(
    request: VideoGenerationRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> VideoGenerationResponse:
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    video_provider = registry.get_video_provider(provider_name)
    
    response = await video_provider.generate_video(
        prompt=request.prompt,
        model=request.model,
        duration=request.duration,
        resolution=request.resolution.value,
        fps=request.fps,
    )
    
    return response


@router.post("/generate/stream")
async def generate_video_stream(
    request: VideoGenerationRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> StreamingResponse:
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    video_provider = registry.get_video_provider(provider_name)

    async def generate():
        async for chunk in video_provider.stream_video_generation(
            prompt=request.prompt,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.post("/from-image", response_model=VideoGenerationResponse)
async def generate_video_from_image(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    duration: float = Form(5.0),
    model: Optional[str] = Form(None),
) -> VideoGenerationResponse:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    video_provider = registry.get_video_provider(provider)
    
    image_data = await image.read()
    
    response = await video_provider.generate_video_from_image(
        image_data=image_data,
        prompt=prompt,
        model=model,
        duration=duration,
    )
    
    return response


@router.post("/analyze", response_model=VideoAnalysisResponse)
async def analyze_video(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    video: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    include_timestamps: bool = Form(False),
    include_transcript: bool = Form(False),
) -> VideoAnalysisResponse:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    video_provider = registry.get_video_provider(provider)
    
    video_data = await video.read()
    
    response = await video_provider.analyze_video(
        video_data=video_data,
        prompt=prompt,
        timestamps=include_timestamps,
    )
    
    return response

