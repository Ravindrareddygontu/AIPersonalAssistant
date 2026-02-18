import time
from datetime import datetime
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

import structlog

from backend.ai_middleware.config import get_settings
from backend.ai_middleware.core.base import ProviderCapability, ProviderInfo
from backend.ai_middleware.core.code import CodeProvider
from backend.ai_middleware.models.base import UsageInfo
from backend.ai_middleware.models.code import (
    CodeAnalysisResponse,
    CodeCompletionResponse,
    CodeGenerationResponse,
    CodeIssue,
    CodeStreamChunk,
)
from backend.ai_middleware.providers.openai.base import OpenAIClientMixin

logger = structlog.get_logger()


class OpenAICodeProvider(CodeProvider, OpenAIClientMixin):

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(api_key=api_key, **kwargs)
        self._settings = get_settings()

    @property
    def default_model(self) -> str:
        return self._settings.openai_code_model

    @property
    def provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="openai-code",
            display_name="OpenAI Code",
            description="OpenAI GPT models optimized for code generation and analysis",
            capabilities=[
                ProviderCapability.CODE_GENERATION,
                ProviderCapability.CODE_COMPLETION,
                ProviderCapability.CODE_ANALYSIS,
            ],
            models=[self.default_model],  # Dynamic from config
            documentation_url="https://platform.openai.com/docs/guides/code-generation",
        )

    async def health_check(self) -> bool:
        try:
            await self._make_request("GET", "/models", timeout=10.0)
            return True
        except Exception:
            return False

    async def generate_code(
        self,
        prompt: str,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeGenerationResponse:
        start_time = time.perf_counter()
        request_id = uuid4()
        model = model or self.default_model

        system_prompt = f"""You are an expert {language} programmer. Generate clean, well-documented,
production-quality code. Follow best practices and include type hints where applicable.
Only output the code without explanations unless specifically asked."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate {language} code for: {prompt}"},
        ]
        
        if kwargs.get("context"):
            messages.insert(1, {"role": "user", "content": f"Context:\n{kwargs['context']}"})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }
        if kwargs.get("max_tokens"):
            payload["max_tokens"] = kwargs["max_tokens"]

        response = await self._make_request("POST", "/chat/completions", payload)
        latency_ms = (time.perf_counter() - start_time) * 1000

        code = response["choices"][0]["message"]["content"]
        
        # Try to extract code from markdown blocks
        if "```" in code:
            lines = code.split("\n")
            in_block = False
            code_lines = []
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    code_lines.append(line)
            if code_lines:
                code = "\n".join(code_lines)

        usage = None
        if "usage" in response:
            usage = UsageInfo(
                prompt_tokens=response["usage"]["prompt_tokens"],
                completion_tokens=response["usage"]["completion_tokens"],
                total_tokens=response["usage"]["total_tokens"],
            )

        return CodeGenerationResponse(
            request_id=request_id,
            provider="openai-code",
            model=response["model"],
            created_at=datetime.utcnow(),
            code=code.strip(),
            language=language,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def complete_code(
        self,
        code_prefix: str,
        code_suffix: Optional[str] = None,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeCompletionResponse:
        start_time = time.perf_counter()
        request_id = uuid4()
        model = model or self.default_model

        if code_suffix:
            prompt = f"Complete the code between PREFIX and SUFFIX:\n\nPREFIX:\n{code_prefix}\n\nSUFFIX:\n{code_suffix}\n\nProvide only the completion code."
        else:
            prompt = f"Complete this {language} code:\n\n{code_prefix}\n\nProvide only the completion."

        messages = [
            {"role": "system", "content": f"You are a {language} code completion assistant. Output only code."},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.0),
            "max_tokens": kwargs.get("max_tokens", 256),
        }

        response = await self._make_request("POST", "/chat/completions", payload)
        latency_ms = (time.perf_counter() - start_time) * 1000
        completion = response["choices"][0]["message"]["content"].strip()

        return CodeCompletionResponse(
            request_id=request_id,
            provider="openai-code",
            model=response["model"],
            created_at=datetime.utcnow(),
            completion=completion,
            language=language,
            finish_reason=response["choices"][0].get("finish_reason"),
            latency_ms=latency_ms,
        )

    async def analyze_code(
        self,
        code: str,
        language: str = "python",
        analysis_type: str = "review",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeAnalysisResponse:
        start_time = time.perf_counter()
        request_id = uuid4()
        model = model or self.default_model

        analysis_prompts = {
            "review": "Review this code for bugs, best practices, and improvements.",
            "security": "Analyze this code for security vulnerabilities and risks.",
            "explain": "Explain what this code does in detail.",
            "optimize": "Suggest optimizations for performance and efficiency.",
            "debug": "Identify potential bugs and issues in this code.",
        }

        system_prompt = f"""You are a senior {language} code reviewer. Analyze the code and provide:
1. A summary of findings
2. List of issues with severity (error/warning/info/suggestion), line numbers if possible
3. Specific suggestions for improvement
Format issues as JSON array."""

        prompt = f"{analysis_prompts.get(analysis_type, analysis_prompts['review'])}\n\n```{language}\n{code}\n```"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        payload = {"model": model, "messages": messages, "temperature": 0.3}
        response = await self._make_request("POST", "/chat/completions", payload)
        latency_ms = (time.perf_counter() - start_time) * 1000

        content = response["choices"][0]["message"]["content"]
        
        # Parse the response - simplified parsing
        issues = []
        suggestions = []
        summary = content[:500] if len(content) > 500 else content

        return CodeAnalysisResponse(
            request_id=request_id,
            provider="openai-code",
            model=response["model"],
            created_at=datetime.utcnow(),
            summary=summary,
            issues=issues,
            suggestions=suggestions,
            latency_ms=latency_ms,
        )

    async def generate_code_stream(
        self,
        prompt: str,
        language: str = "python",
        **kwargs: Any,
    ) -> AsyncIterator[CodeStreamChunk]:
        request_id = uuid4()
        model = kwargs.get("model") or self.default_model

        system_prompt = f"You are an expert {language} programmer. Generate clean code. Output only code."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate {language} code for: {prompt}"},
        ]

        payload = {"model": model, "messages": messages, "temperature": 0.2}
        index = 0

        async for data in self._stream_request("/chat/completions", payload):
            if "choices" in data and data["choices"]:
                delta = data["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield CodeStreamChunk(
                        request_id=request_id,
                        index=index,
                        content=content,
                        language=language,
                        is_final=data["choices"][0].get("finish_reason") is not None,
                    )
                    index += 1

