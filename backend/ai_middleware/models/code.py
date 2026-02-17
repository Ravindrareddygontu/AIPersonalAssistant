"""Code generation, completion, and analysis models."""

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.ai_middleware.models.base import BaseRequest, BaseResponse, StreamEvent


class ProgrammingLanguage(str, Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    SCALA = "scala"
    R = "r"
    SQL = "sql"
    SHELL = "shell"
    HTML = "html"
    CSS = "css"


class CodeAnalysisType(str, Enum):
    """Types of code analysis."""

    REVIEW = "review"
    SECURITY = "security"
    EXPLAIN = "explain"
    OPTIMIZE = "optimize"
    DEBUG = "debug"
    DOCUMENT = "document"
    TEST = "test"


class CodeGenerationRequest(BaseRequest):
    """Code generation request."""

    prompt: str
    language: str = "python"
    context: Optional[str] = None  # Existing code context
    max_tokens: Optional[int] = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    include_explanation: bool = False
    include_tests: bool = False


class CodeCompletionRequest(BaseRequest):
    """Code completion request (fill-in-middle)."""

    code_prefix: str
    code_suffix: Optional[str] = None
    language: str = "python"
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    stop_sequences: Optional[list[str]] = None


class CodeAnalysisRequest(BaseRequest):
    """Code analysis request."""

    code: str
    language: str = "python"
    analysis_type: CodeAnalysisType = CodeAnalysisType.REVIEW
    context: Optional[str] = None
    focus_areas: Optional[list[str]] = None  # e.g., ["performance", "security"]


class CodeExecutionRequest(BaseRequest):
    """Code execution request."""

    code: str
    language: str = "python"
    stdin: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    memory_limit_mb: int = Field(default=256, ge=64, le=2048)


class CodeGenerationResponse(BaseResponse):
    """Code generation response."""

    code: str
    language: str
    explanation: Optional[str] = None
    tests: Optional[str] = None
    imports: Optional[list[str]] = None
    dependencies: Optional[list[str]] = None


class CodeCompletionResponse(BaseResponse):
    """Code completion response."""

    completion: str
    language: str
    finish_reason: Optional[str] = None


class CodeIssue(BaseModel):
    """A code issue found during analysis."""

    severity: str  # "error", "warning", "info", "suggestion"
    message: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    column_start: Optional[int] = None
    column_end: Optional[int] = None
    rule_id: Optional[str] = None
    fix_suggestion: Optional[str] = None


class CodeAnalysisResponse(BaseResponse):
    """Code analysis response."""

    summary: str
    issues: list[CodeIssue]
    suggestions: Optional[list[str]] = None
    metrics: Optional[dict[str, float]] = None  # e.g., complexity, coverage
    refactored_code: Optional[str] = None


class CodeExecutionResponse(BaseResponse):
    """Code execution response."""

    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    memory_used_mb: Optional[float] = None
    timed_out: bool = False


class CodeStreamChunk(StreamEvent):
    """A chunk of streaming code generation."""

    event_type: str = "code.chunk"
    content: str
    language: Optional[str] = None

