"""Data models for AI Middleware."""

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, UsageInfo
from backend.ai_middleware.models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
)
from backend.ai_middleware.models.voice import (
    TextToVoiceRequest,
    TextToVoiceResponse,
    VoiceToTextRequest,
    VoiceToTextResponse,
    VoiceStreamChunk,
)
from backend.ai_middleware.models.image import (
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    ImageEditRequest,
    ImageEditResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from backend.ai_middleware.models.video import (
    VideoAnalysisRequest,
    VideoAnalysisResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStreamChunk,
)
from backend.ai_middleware.models.code import (
    CodeAnalysisRequest,
    CodeAnalysisResponse,
    CodeCompletionRequest,
    CodeCompletionResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
    CodeStreamChunk,
)

__all__ = [
    # Base
    "BaseRequest",
    "BaseResponse",
    "UsageInfo",
    # Chat
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatStreamChunk",
    # Voice
    "TextToVoiceRequest",
    "TextToVoiceResponse",
    "VoiceToTextRequest",
    "VoiceToTextResponse",
    "VoiceStreamChunk",
    # Image
    "ImageAnalysisRequest",
    "ImageAnalysisResponse",
    "ImageEditRequest",
    "ImageEditResponse",
    "ImageGenerationRequest",
    "ImageGenerationResponse",
    # Video
    "VideoAnalysisRequest",
    "VideoAnalysisResponse",
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    "VideoStreamChunk",
    # Code
    "CodeAnalysisRequest",
    "CodeAnalysisResponse",
    "CodeCompletionRequest",
    "CodeCompletionResponse",
    "CodeExecutionRequest",
    "CodeExecutionResponse",
    "CodeGenerationRequest",
    "CodeGenerationResponse",
    "CodeStreamChunk",
]

