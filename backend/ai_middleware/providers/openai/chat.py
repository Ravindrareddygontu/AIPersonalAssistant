import time
from datetime import datetime
from typing import Any, AsyncIterator, List, Optional
from uuid import uuid4

import structlog

from backend.ai_middleware.config import get_settings
from backend.ai_middleware.core.base import ProviderCapability, ProviderInfo
from backend.ai_middleware.core.chat import ChatProvider
from backend.ai_middleware.models.base import UsageInfo
from backend.ai_middleware.models.chat import (
    ChatChoice,
    ChatMessage,
    ChatResponse,
    ChatStreamChunk,
    ChatStreamChoice,
    ChatStreamDelta,
    MessageRole,
)
from backend.ai_middleware.providers.openai.base import OpenAIClientMixin

logger = structlog.get_logger()


class OpenAIChatProvider(ChatProvider, OpenAIClientMixin):

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(api_key=api_key, **kwargs)
        self._settings = get_settings()

    @property
    def default_model(self) -> str:
        return self._settings.openai_chat_model

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="openai-chat",
            display_name="OpenAI Chat",
            description="OpenAI GPT models for chat completions",
            capabilities=[
                ProviderCapability.CHAT,
                ProviderCapability.CHAT_STREAMING,
            ],
            models=[self.default_model],  # Dynamic from config
            documentation_url="https://platform.openai.com/docs/api-reference/chat",
        )

    async def health_check(self) -> bool:
        try:
            await self._make_request("GET", "/models", timeout=10.0)
            return True
        except Exception:
            return False

    def _format_messages(self, messages: List[ChatMessage]) -> List[dict]:
        formatted = []
        for msg in messages:
            m = {"role": msg.role, "content": msg.content}
            if msg.name:
                m["name"] = msg.name
            if msg.tool_calls:
                m["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            formatted.append(m)
        return formatted

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        start_time = time.perf_counter()
        request_id = uuid4()
        
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # Add optional parameters
        for key in ["top_p", "frequency_penalty", "presence_penalty", "stop", "tools", "tool_choice"]:
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        response = await self._make_request("POST", "/chat/completions", payload)
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Parse response
        choices = [
            ChatChoice(
                index=choice["index"],
                message=ChatMessage(
                    role=MessageRole(choice["message"]["role"]),
                    content=choice["message"].get("content"),
                    tool_calls=choice["message"].get("tool_calls"),
                ),
                finish_reason=choice.get("finish_reason"),
            )
            for choice in response["choices"]
        ]
        
        usage = None
        if "usage" in response:
            usage = UsageInfo(
                prompt_tokens=response["usage"]["prompt_tokens"],
                completion_tokens=response["usage"]["completion_tokens"],
                total_tokens=response["usage"]["total_tokens"],
            )

        return ChatResponse(
            request_id=request_id,
            provider="openai-chat",
            model=response["model"],
            created_at=datetime.utcnow(),
            choices=choices,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatStreamChunk]:
        request_id = uuid4()
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        index = 0
        async for data in self._stream_request("/chat/completions", payload):
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                delta = choice.get("delta", {})
                
                yield ChatStreamChunk(
                    request_id=request_id,
                    index=index,
                    choices=[
                        ChatStreamChoice(
                            index=choice["index"],
                            delta=ChatStreamDelta(
                                role=delta.get("role"),
                                content=delta.get("content"),
                                tool_calls=delta.get("tool_calls"),
                            ),
                            finish_reason=choice.get("finish_reason"),
                        )
                    ],
                    is_final=choice.get("finish_reason") is not None,
                )
                index += 1

