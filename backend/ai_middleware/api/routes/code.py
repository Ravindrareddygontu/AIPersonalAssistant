"""Code generation, completion, and analysis routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.ai_middleware.api.dependencies import ApiKeyDep, ProviderDep, RegistryDep
from backend.ai_middleware.models.code import (
    CodeAnalysisRequest,
    CodeAnalysisResponse,
    CodeCompletionRequest,
    CodeCompletionResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
)

router = APIRouter()


@router.post("/generate", response_model=CodeGenerationResponse)
async def generate_code(
    request: CodeGenerationRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> CodeGenerationResponse:
    """
    Generate code from a natural language prompt.
    
    Describe what you want and get code in the specified language.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    code_provider = registry.get_code_provider(provider_name)
    
    response = await code_provider.generate_code(
        prompt=request.prompt,
        language=request.language,
        model=request.model,
    )
    
    return response


@router.post("/generate/stream")
async def generate_code_stream(
    request: CodeGenerationRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> StreamingResponse:
    """
    Stream code generation.
    
    Returns Server-Sent Events with code chunks.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    code_provider = registry.get_code_provider(provider_name)

    async def generate():
        async for chunk in code_provider.generate_code_stream(
            prompt=request.prompt,
            language=request.language,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.post("/complete", response_model=CodeCompletionResponse)
async def complete_code(
    request: CodeCompletionRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> CodeCompletionResponse:
    """
    Complete code given a prefix and optional suffix.
    
    Supports fill-in-the-middle completion.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    code_provider = registry.get_code_provider(provider_name)
    
    response = await code_provider.complete_code(
        code_prefix=request.code_prefix,
        code_suffix=request.code_suffix,
        language=request.language,
        model=request.model,
    )
    
    return response


@router.post("/analyze", response_model=CodeAnalysisResponse)
async def analyze_code(
    request: CodeAnalysisRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> CodeAnalysisResponse:
    """
    Analyze code for issues, security problems, or get explanations.
    
    Supports different analysis types: review, security, explain, optimize.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    code_provider = registry.get_code_provider(provider_name)
    
    response = await code_provider.analyze_code(
        code=request.code,
        language=request.language,
        analysis_type=request.analysis_type.value,
        model=request.model,
    )
    
    return response


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    registry: RegistryDep,
    api_key: ApiKeyDep,
    provider: ProviderDep,
) -> CodeExecutionResponse:
    """
    Execute code in a sandboxed environment.
    
    Returns stdout, stderr, and exit code.
    """
    provider_name = provider or request.provider
    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be specified",
        )
    
    code_provider = registry.get_code_provider(provider_name)
    
    response = await code_provider.execute_code(
        code=request.code,
        language=request.language,
        timeout=request.timeout_seconds,
    )
    
    return response

