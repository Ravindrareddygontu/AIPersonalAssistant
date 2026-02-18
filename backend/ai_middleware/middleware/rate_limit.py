import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.ai_middleware.config import get_settings

logger = structlog.get_logger()


@dataclass
class RateLimitState:
    requests: int = 0
    window_start: float = field(default_factory=time.time)


class InMemoryRateLimiter:

    def __init__(
        self,
        requests_per_window: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._state: Dict[str, RateLimitState] = defaultdict(RateLimitState)

    def _get_key(self, request: Request) -> str:
        # Use API key if present, otherwise use IP
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key[:16]}"  # Use prefix of API key
        
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def check(self, request: Request) -> tuple[bool, int, int]:
        key = self._get_key(request)
        now = time.time()
        state = self._state[key]
        
        # Reset window if expired
        if now - state.window_start >= self.window_seconds:
            state.requests = 0
            state.window_start = now
        
        # Check limit
        remaining = max(0, self.requests_per_window - state.requests)
        reset_after = int(self.window_seconds - (now - state.window_start))
        
        if state.requests >= self.requests_per_window:
            return False, remaining, reset_after
        
        # Increment counter
        state.requests += 1
        remaining = max(0, self.requests_per_window - state.requests)
        
        return True, remaining, reset_after


class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(
        self,
        app,
        requests_per_window: Optional[int] = None,
        window_seconds: Optional[int] = None,
        exclude_paths: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        settings = get_settings()
        self.limiter = InMemoryRateLimiter(
            requests_per_window=requests_per_window or settings.rate_limit_requests,
            window_seconds=window_seconds or settings.rate_limit_window_seconds,
        )
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/openapi.json"]

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        allowed, remaining, reset_after = self.limiter.check(request)
        
        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                path=request.url.path,
                client=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded. Please try again later.",
                    "details": {
                        "retry_after": reset_after,
                    },
                },
                headers={
                    "Retry-After": str(reset_after),
                    "X-RateLimit-Limit": str(self.limiter.requests_per_window),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_after),
                },
            )
        
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.limiter.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_after)
        
        return response

