from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


class AIMiddlewareException(Exception):

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[UUID] = None,
        provider: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id
        self.provider = provider

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_code,
            "error_code": self.error_code,
            "message": self.message,
            "request_id": str(self.request_id) if self.request_id else None,
            "provider": self.provider,
            "details": self.details,
        }


class ProviderError(AIMiddlewareException):

    def __init__(
        self,
        message: str,
        provider: str,
        original_error: Optional[Exception] = None,
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message=message,
            error_code="PROVIDER_ERROR",
            status_code=status_code,
            provider=provider,
            **kwargs,
        )
        self.original_error = original_error


class RateLimitError(AIMiddlewareException):

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            **kwargs,
        )
        self.retry_after = retry_after


class ValidationError(AIMiddlewareException):

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            **kwargs,
        )


class AuthenticationError(AIMiddlewareException):

    def __init__(self, message: str = "Authentication failed", **kwargs: Any) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            **kwargs,
        )


class NotFoundError(AIMiddlewareException):

    def __init__(self, message: str, resource: Optional[str] = None, **kwargs: Any) -> None:
        details = kwargs.pop("details", {})
        if resource:
            details["resource"] = resource
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            **kwargs,
        )


async def error_handler_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except AIMiddlewareException as e:
        logger.error(
            "AI Middleware error",
            error_code=e.error_code,
            message=e.message,
            provider=e.provider,
            request_id=str(e.request_id) if e.request_id else None,
        )
        response = JSONResponse(
            status_code=e.status_code,
            content=e.to_dict(),
        )
        if isinstance(e, RateLimitError) and e.retry_after:
            response.headers["Retry-After"] = str(e.retry_after)
        return response
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"type": type(e).__name__} if logger.isEnabledFor(10) else {},
            },
        )


def setup_error_handlers(app: FastAPI) -> None:
    app.middleware("http")(error_handler_middleware)

