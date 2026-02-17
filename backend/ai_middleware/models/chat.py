"""Chat/conversation models."""

from enum import Enum
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class MessageRole(str, Enum):
    """Role of a message sender."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class ContentPart(BaseModel):
    """Multimodal content part."""

    type: str  # "text", "image_url", "audio"
    text: Optional[str] = None
    image_url: Optional[dict[str, str]] = None
    audio: Optional[dict[str, str]] = None


class ToolCall(BaseModel):
    """A tool/function call made by the model."""

    id: str
    type: str = "function"
    function: dict[str, Any]


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    role: MessageRole
    content: Union[str, list[ContentPart], None] = None
    name: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None

    class Config:
        use_enum_values = True


class ToolDefinition(BaseModel):
    """Definition of a tool the model can use."""

    type: str = "function"
    function: dict[str, Any]


class ChatRequest(BaseRequest):
    """Chat completion request."""

    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    stop: Optional[list[str]] = None
    stream: bool = False
    tools: Optional[list[ToolDefinition]] = None
    tool_choice: Optional[Union[str, dict[str, Any]]] = None
    response_format: Optional[dict[str, str]] = None


class ChatChoice(BaseModel):
    """A single choice/response in a chat completion."""

    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatResponse(BaseResponse):
    """Chat completion response."""

    choices: list[ChatChoice]
    
    @property
    def content(self) -> Optional[str]:
        """Get the content of the first choice."""
        if self.choices and self.choices[0].message.content:
            content = self.choices[0].message.content
            return content if isinstance(content, str) else None
        return None

    @property
    def message(self) -> Optional[ChatMessage]:
        """Get the first message."""
        return self.choices[0].message if self.choices else None


class ChatStreamDelta(BaseModel):
    """Delta content in a streaming response."""

    role: Optional[MessageRole] = None
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None


class ChatStreamChoice(BaseModel):
    """A single choice in a streaming response."""

    index: int = 0
    delta: ChatStreamDelta
    finish_reason: Optional[str] = None


class ChatStreamChunk(StreamEvent):
    """A chunk of a streaming chat response."""

    event_type: str = "chat.chunk"
    choices: list[ChatStreamChoice]

    @property
    def content(self) -> Optional[str]:
        """Get the delta content of the first choice."""
        if self.choices and self.choices[0].delta.content:
            return self.choices[0].delta.content
        return None

