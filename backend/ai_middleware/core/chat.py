from abc import abstractmethod
from typing import Any, AsyncIterator, Optional

from backend.ai_middleware.core.base import BaseProvider, StreamingMixin
from backend.ai_middleware.models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
)


class ChatProvider(BaseProvider, StreamingMixin):

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        ...
        yield  # Make this a generator

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        messages = [ChatMessage(role="user", content=prompt)]
        return await self.chat(messages, model=model, **kwargs)

    def create_request(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ChatRequest:
        return ChatRequest(
            messages=messages,
            model=model or self.provider_info.models[0],
            provider=self.name,
            **kwargs,
        )

