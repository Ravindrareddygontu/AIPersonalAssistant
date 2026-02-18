from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.ai_middleware import __version__
from backend.ai_middleware.api.router import create_router
from backend.ai_middleware.config import get_settings
from backend.ai_middleware.middleware.error_handler import setup_error_handlers
from backend.ai_middleware.middleware.logging import LoggingMiddleware, setup_logging
from backend.ai_middleware.middleware.rate_limit import RateLimitMiddleware
from backend.ai_middleware.providers.registry import get_registry

logger = structlog.get_logger()


def register_openai_providers() -> None:
    from backend.ai_middleware.providers.openai import (
        OpenAIChatProvider,
        OpenAICodeProvider,
        OpenAIImageProvider,
        OpenAIVoiceProvider,
    )

    settings = get_settings()
    registry = get_registry()

    # Only register if API key is available
    if settings.openai_api_key:
        config = {"api_key": settings.openai_api_key}

        registry.register(OpenAIChatProvider, config)
        registry.register(OpenAIVoiceProvider, config)
        registry.register(OpenAIImageProvider, config)
        registry.register(OpenAICodeProvider, config)

        logger.info("OpenAI providers registered")
    else:
        logger.warning("OpenAI API key not configured, providers not registered")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # Setup logging
    setup_logging()

    logger.info(
        "Starting AI Middleware",
        version=__version__,
        environment=settings.app_env,
    )

    # Register providers
    register_openai_providers()

    # Initialize provider registry
    registry = get_registry()
    logger.info(
        "Provider registry initialized",
        registered_providers=len(registry.list_providers()),
        providers=[p.name for p in registry.list_providers()],
    )

    yield

    # Cleanup
    logger.info("Shutting down AI Middleware")


def create_app() -> FastAPI:
    settings = get_settings()
    
    app = FastAPI(
        title="AI Middleware",
        description="A unified middleware infrastructure for AI model APIs",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add custom middleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_window=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    
    # Setup error handlers
    setup_error_handlers(app)
    
    # Include API routes
    router = create_router()
    app.include_router(router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": __version__,
            "environment": settings.app_env,
        }
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "AI Middleware",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
            "api": "/api/v1",
        }
    
    return app


# Create app instance
app = create_app()


def main() -> None:
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "ai_middleware.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()

