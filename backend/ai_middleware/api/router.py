from fastapi import APIRouter

from backend.ai_middleware.api.routes import chat, code, image, providers, video, voice


def create_router() -> APIRouter:
    router = APIRouter()

    # Include all route modules
    router.include_router(
        providers.router,
        prefix="/providers",
        tags=["Providers"],
    )
    router.include_router(
        chat.router,
        prefix="/chat",
        tags=["Chat"],
    )
    router.include_router(
        voice.router,
        prefix="/voice",
        tags=["Voice"],
    )
    router.include_router(
        image.router,
        prefix="/image",
        tags=["Image"],
    )
    router.include_router(
        video.router,
        prefix="/video",
        tags=["Video"],
    )
    router.include_router(
        code.router,
        prefix="/code",
        tags=["Code"],
    )

    return router

