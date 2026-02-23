from typing import Optional, List
from pydantic import BaseModel


class ChatStreamRequest(BaseModel):
    message: str
    workspace: Optional[str] = None
    chatId: Optional[str] = None
    history: Optional[List[dict]] = None
    provider: Optional[str] = None


class ChatResetRequest(BaseModel):
    workspace: Optional[str] = None
    provider: Optional[str] = None

