from enum import Enum
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class MessageRole(str, Enum):

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class ContentPart(BaseModel):

    type: str
    text: Optional[str] = None
    image_url: Optional[dict[str, str]] = None
    audio: Optional[dict[str, str]] = None


class ToolCall(BaseModel):

    id: str
    type: str = "function"
    function: dict[str, Any]


class ChatMessage(BaseModel):

    role: MessageRole
    content: Union[str, list[ContentPart], None] = None
    name: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None

    class Config:
        use_enum_values = True


class ToolDefinition(BaseModel):

    type: str = "function"
    function: dict[str, Any]


class ChatRequest(BaseRequest):

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

    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatResponse(BaseResponse):

    choices: list[ChatChoice]

    @property
    def content(self) -> Optional[str]:
        if self.choices and self.choices[0].message.content:
            content = self.choices[0].message.content
            return content if isinstance(content, str) else None
        return None

    @property
    def message(self) -> Optional[ChatMessage]:
        return self.choices[0].message if self.choices else None


class ChatStreamDelta(BaseModel):

    role: Optional[MessageRole] = None
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None


class ChatStreamChoice(BaseModel):

    index: int = 0
    delta: ChatStreamDelta
    finish_reason: Optional[str] = None


class ChatStreamChunk(StreamEvent):

    event_type: str = "chat.chunk"
    choices: list[ChatStreamChoice]

    @property
    def content(self) -> Optional[str]:
        if self.choices and self.choices[0].delta.content:
            return self.choices[0].delta.content
        return None

