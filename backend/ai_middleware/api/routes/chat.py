from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.ai_middleware.api.dependencies import ApiKeyDep, ProviderDep, RegistryDep
from backend.ai_middleware.models.chat import ChatMessage, ChatRequest, ChatResponse

router = APIRouter()


@router.post("/completions", response_model=ChatResponse)
async def create_chat_completion(
    request: ChatRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> ChatResponse:
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified in request body or X-Provider header",
        )
    
    if not registry.has_provider(provider_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    
    chat_provider = registry.get_chat_provider(provider_name)
    
    response = await chat_provider.chat(
        messages=request.messages,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        frequency_penalty=request.frequency_penalty,
        presence_penalty=request.presence_penalty,
        stop=request.stop,
    )
    
    return response


@router.post("/completions/stream")
async def create_chat_completion_stream(
    request: ChatRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> StreamingResponse:
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified in request body or X-Provider header",
        )
    
    if not registry.has_provider(provider_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    
    chat_provider = registry.get_chat_provider(provider_name)

    async def generate():
        async for chunk in chat_provider.chat_stream(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/complete")
async def simple_completion(
    prompt: str,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> dict:
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified via X-Provider header or provider query param",
        )
    
    chat_provider = registry.get_chat_provider(provider)
    response = await chat_provider.complete(
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    return {
        "text": response.content,
        "model": response.model,
        "usage": response.usage.model_dump() if response.usage else None,
    }

