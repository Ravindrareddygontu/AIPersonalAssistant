"""Logging middleware and configuration."""

import json
import time
from typing import Callable
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from backend.ai_middleware.config import get_settings

# 1MB threshold for truncation
MAX_LOG_SIZE_BYTES = 1024 * 1024  # 1MB
TRUNCATED_CHARS = 200


def truncate_log_data(data: str) -> str:
    """Truncate data if it exceeds 1MB, showing only 200 chars."""
    if len(data.encode('utf-8')) > MAX_LOG_SIZE_BYTES:
        return f"{data[:TRUNCATED_CHARS]}... [TRUNCATED - original size: {len(data)} chars]"
    return data


def setup_logging() -> None:
    """Configure structured logging."""
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            (
                structlog.dev.ConsoleRenderer()
                if settings.is_development
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.stdlib.NAME_TO_LEVEL[settings.log_level.lower()]
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging with body capture."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Log request and response details including bodies."""
        logger = structlog.get_logger()

        # Generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid4()))

        # Bind request context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        # Read and log request body
        request_body = ""
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                request_body = body_bytes.decode("utf-8")
            except Exception:
                request_body = "[unable to read body]"

        # Log request with body
        logger.info(
            "Request started",
            query_params=dict(request.query_params),
            user_agent=request.headers.get("user-agent"),
            request_body=truncate_log_data(request_body) if request_body else None,
        )

        # Time the request
        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Capture response body
            response_body = ""
            if not isinstance(response, StreamingResponse):
                # Read response body
                response_body_bytes = b""
                async for chunk in response.body_iterator:
                    response_body_bytes += chunk
                response_body = response_body_bytes.decode("utf-8")

                # Recreate response with the body
                from starlette.responses import Response as StarletteResponse
                response = StarletteResponse(
                    content=response_body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            # Log response with body
            logger.info(
                "Request completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                response_body=truncate_log_data(response_body) if response_body else "[streaming]",
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request failed",
                error=str(e),
                duration_ms=round(duration_ms, 2),
            )
            raise


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add request context for downstream use."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Add request context."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        
        # Store in request state for downstream access
        request.state.request_id = request_id
        request.state.start_time = time.perf_counter()
        
        response = await call_next(request)
        return response

