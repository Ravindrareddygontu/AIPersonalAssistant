from typing import Any, AsyncIterator, Dict, Optional

import httpx
import structlog

from backend.ai_middleware.config import get_settings
from backend.ai_middleware.middleware.error_handler import ProviderError

logger = structlog.get_logger()

# OpenAI API endpoints
OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIClientMixin:

    api_key: Optional[str]
    config: Dict[str, Any]

    def _get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        settings = get_settings()
        if settings.openai_api_key:
            return settings.openai_api_key
        raise ProviderError(
            message="OpenAI API key not configured",
            provider="openai",
        )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
        }

    def _get_base_url(self) -> str:
        return self.config.get("base_url", OPENAI_BASE_URL)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        url = f"{self._get_base_url()}{endpoint}"
        headers = self._get_headers()
        
        if files:
            # Remove Content-Type for multipart uploads
            headers.pop("Content-Type", None)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                if files:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        files=files,
                        data=json_data,
                    )
                else:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=json_data,
                    )
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                error_body = e.response.text
                logger.error(
                    "OpenAI API error",
                    status_code=e.response.status_code,
                    error=error_body,
                )
                raise ProviderError(
                    message=f"OpenAI API error: {error_body}",
                    provider="openai",
                    original_error=e,
                    status_code=e.response.status_code,
                )
            except httpx.RequestError as e:
                logger.error("OpenAI request failed", error=str(e))
                raise ProviderError(
                    message=f"Failed to connect to OpenAI: {str(e)}",
                    provider="openai",
                    original_error=e,
                )

    async def _stream_request(
        self,
        endpoint: str,
        json_data: Dict[str, Any],
        timeout: float = 120.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        url = f"{self._get_base_url()}{endpoint}"
        headers = self._get_headers()
        json_data["stream"] = True

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=json_data,
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            break
                        try:
                            import json
                            yield json.loads(data)
                        except Exception:
                            continue

    async def _download_binary(
        self,
        url: str,
        timeout: float = 60.0,
    ) -> bytes:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

