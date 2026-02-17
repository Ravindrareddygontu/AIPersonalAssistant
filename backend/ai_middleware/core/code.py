"""Code provider abstraction."""

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
    """Abstract base class for code AI providers."""

    @abstractmethod
    async def generate_code(
        self,
        prompt: str,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeGenerationResponse:
        """
        Generate code from a natural language prompt.

        Args:
            prompt: Description of the code to generate
            language: Target programming language
            model: Model to use (provider-specific)
            **kwargs: Additional provider-specific parameters

        Returns:
            CodeGenerationResponse with generated code
        """
        ...

    async def complete_code(
        self,
        code_prefix: str,
        code_suffix: Optional[str] = None,
        language: str = "python",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeCompletionResponse:
        """
        Complete code given prefix and optional suffix.

        Args:
            code_prefix: Code before cursor position
            code_suffix: Code after cursor position (fill-in-middle)
            language: Programming language
            model: Model to use
            **kwargs: Additional parameters

        Returns:
            CodeCompletionResponse with completion
        """
        raise NotImplementedError("Code completion not supported by this provider")

    async def analyze_code(
        self,
        code: str,
        language: str = "python",
        analysis_type: str = "review",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> CodeAnalysisResponse:
        """
        Analyze code for issues, improvements, or explanations.

        Args:
            code: Source code to analyze
            language: Programming language
            analysis_type: Type of analysis ("review", "security", "explain", "optimize")
            model: Model to use
            **kwargs: Additional parameters

        Returns:
            CodeAnalysisResponse with analysis
        """
        raise NotImplementedError("Code analysis not supported by this provider")

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        **kwargs: Any,
    ) -> CodeExecutionResponse:
        """
        Execute code in a sandboxed environment.

        Args:
            code: Source code to execute
            language: Programming language
            timeout: Execution timeout in seconds
            **kwargs: Additional parameters

        Returns:
            CodeExecutionResponse with execution results
        """
        raise NotImplementedError("Code execution not supported by this provider")

    async def generate_code_stream(
        self,
        prompt: str,
        language: str = "python",
        **kwargs: Any,
    ) -> AsyncIterator[CodeStreamChunk]:
        """
        Stream code generation.

        Args:
            prompt: Description of code to generate
            language: Target language
            **kwargs: Additional parameters

        Yields:
            CodeStreamChunk objects as code is generated
        """
        raise NotImplementedError("Streaming code generation not supported")
        yield  # Make this a generator

    def create_generation_request(
        self, prompt: str, language: str = "python", **kwargs: Any
    ) -> CodeGenerationRequest:
        """Create a CodeGenerationRequest object."""
        return CodeGenerationRequest(
            prompt=prompt, language=language, provider=self.name, **kwargs
        )

    def create_completion_request(
        self, code_prefix: str, **kwargs: Any
    ) -> CodeCompletionRequest:
        """Create a CodeCompletionRequest object."""
        return CodeCompletionRequest(
            code_prefix=code_prefix, provider=self.name, **kwargs
        )

    def create_analysis_request(self, code: str, **kwargs: Any) -> CodeAnalysisRequest:
        """Create a CodeAnalysisRequest object."""
        return CodeAnalysisRequest(code=code, provider=self.name, **kwargs)

    def create_execution_request(
        self, code: str, **kwargs: Any
    ) -> CodeExecutionRequest:
        """Create a CodeExecutionRequest object."""
        return CodeExecutionRequest(code=code, provider=self.name, **kwargs)

