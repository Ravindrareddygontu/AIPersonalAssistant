"""Chat provider abstraction."""

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
    """Abstract base class for chat/conversation AI providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """
        Send a chat request and get a response.

        Args:
            messages: List of chat messages in the conversation
            model: Model to use (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Returns:
            ChatResponse with the model's reply
        """
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
        """
        Stream a chat response.

        Args:
            messages: List of chat messages in the conversation
            model: Model to use (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Yields:
            ChatStreamChunk objects as they arrive
        """
        ...
        yield  # Make this a generator

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """
        Simple completion interface (wraps chat).

        Args:
            prompt: The prompt to complete
            model: Model to use
            **kwargs: Additional parameters

        Returns:
            ChatResponse with the completion
        """
        messages = [ChatMessage(role="user", content=prompt)]
        return await self.chat(messages, model=model, **kwargs)

    def create_request(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ChatRequest:
        """Create a ChatRequest object."""
        return ChatRequest(
            messages=messages,
            model=model or self.provider_info.models[0],
            provider=self.name,
            **kwargs,
        )

