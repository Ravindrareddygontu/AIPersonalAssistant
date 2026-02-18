from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class UsageInfo(BaseModel):

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None

    @property
    def total(self) -> int:
        return self.total_tokens or (self.prompt_tokens + self.completion_tokens)


class BaseRequest(BaseModel):

    request_id: UUID = Field(default_factory=uuid4)
    provider: Optional[str] = None
    model: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class BaseResponse(BaseModel):

    request_id: UUID
    provider: str
    model: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    usage: Optional[UsageInfo] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: Optional[float] = None

    class Config:
        extra = "allow"


class ErrorResponse(BaseModel):

    error: str
    error_code: str
    message: str
    request_id: Optional[UUID] = None
    provider: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):

    event_type: str
    request_id: UUID
    index: int = 0
    is_final: bool = False

