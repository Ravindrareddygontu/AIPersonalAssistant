"""Voice/speech routes."""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from backend.ai_middleware.api.dependencies import ApiKeyDep, ProviderDep, RegistryDep
from backend.ai_middleware.models.voice import (
    TextToVoiceRequest,
    TextToVoiceResponse,
    VoiceToTextResponse,
)

router = APIRouter()


@router.post("/transcribe", response_model=VoiceToTextResponse)
async def transcribe_audio(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
) -> VoiceToTextResponse:
    """
    Transcribe audio to text (Speech-to-Text).
    
    Upload an audio file and get the transcription.
    """
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified via X-Provider header",
        )
    
    voice_provider = registry.get_voice_provider(provider)
    
    # Read audio data
    audio_data = await file.read()
    
    # Determine audio format from filename
    audio_format = "wav"
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext in ["mp3", "wav", "webm", "ogg", "flac", "m4a"]:
            audio_format = ext
    
    response = await voice_provider.voice_to_text(
        audio_data=audio_data,
        audio_format=audio_format,
        language=language,
        model=model,
    )
    
    return response


@router.post("/synthesize")
async def synthesize_speech(
    request: TextToVoiceRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> Response:
    """
    Convert text to speech (Text-to-Speech).
    
    Returns audio data in the requested format.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    voice_provider = registry.get_voice_provider(provider_name)
    
    response = await voice_provider.text_to_voice(
        text=request.text,
        voice=request.voice,
        model=request.model,
        output_format=request.output_format.value,
        speed=request.speed,
    )
    
    return Response(
        content=response.audio_data,
        media_type=response.content_type,
        headers={
            "Content-Disposition": f"attachment; filename=speech.{response.audio_format.value}",
        },
    )


@router.post("/synthesize/stream")
async def synthesize_speech_stream(
    request: TextToVoiceRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> StreamingResponse:
    """
    Stream text-to-speech audio.
    
    Returns audio chunks as they're generated.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    voice_provider = registry.get_voice_provider(provider_name)

    async def generate():
        async for chunk in voice_provider.text_to_voice_stream(
            text=request.text,
            voice=request.voice,
            model=request.model,
        ):
            yield chunk.audio_chunk

    return StreamingResponse(
        generate(),
        media_type=f"audio/{request.output_format.value}",
    )


@router.get("/voices")
async def list_voices(
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> dict:
    """List available voices for a provider."""
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    voice_provider = registry.get_voice_provider(provider)
    info = voice_provider.provider_info
    
    return {
        "provider": info.name,
        "voices": info.models,  # Voices are typically listed in models
    }

