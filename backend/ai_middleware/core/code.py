from abc import abstractmethod
from typing import Any, AsyncIterator, Optional

from backend.ai_middleware.core.base import BaseProvider, StreamingMixin
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


class CodeProvider(BaseProvider, StreamingMixin):

    @abstractmethod
    async def generate_code(
        self,
        prompt: str,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeGenerationResponse:
        ...

    async def complete_code(
        self,
        code_prefix: str,
        code_suffix: Optional[str] = None,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeCompletionResponse:
        raise NotImplementedError("Code completion not supported by this provider")

    async def analyze_code(
        self,
        code: str,
        language: str = "python",
        analysis_type: str = "review",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeAnalysisResponse:
        raise NotImplementedError("Code analysis not supported by this provider")

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        **kwargs: Any,
    ) -> CodeExecutionResponse:
        raise NotImplementedError("Code execution not supported by this provider")

    async def generate_code_stream(
        self,
        prompt: str,
        language: str = "python",
        **kwargs: Any,
    ) -> AsyncIterator[CodeStreamChunk]:
        raise NotImplementedError("Streaming code generation not supported")
        yield  # Make this a generator

    def create_generation_request(
        self, prompt: str, language: str = "python", **kwargs: Any
    ) -> CodeGenerationRequest:
        return CodeGenerationRequest(
            prompt=prompt, language=language, provider=self.name, **kwargs
        )

    def create_completion_request(
        self, code_prefix: str, **kwargs: Any
    ) -> CodeCompletionRequest:
        return CodeCompletionRequest(
            code_prefix=code_prefix, provider=self.name, **kwargs
        )

    def create_analysis_request(self, code: str, **kwargs: Any) -> CodeAnalysisRequest:
        return CodeAnalysisRequest(code=code, provider=self.name, **kwargs)

    def create_execution_request(
        self, code: str, **kwargs: Any
    ) -> CodeExecutionRequest:
        return CodeExecutionRequest(code=code, provider=self.name, **kwargs)

