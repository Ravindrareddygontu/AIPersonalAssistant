"""Routes module - FastAPI routers for all API endpoints."""
from fastapi import FastAPI

from backend.routes.main import main_router, set_templates
from backend.routes.settings import settings_router
from backend.routes.chat import chat_router
from backend.routes.notifications import notifications_router
from backend.routes.speech import speech_router


def register_routes(app: FastAPI):
    """Register all FastAPI routers with the application."""
    app.include_router(main_router)
    app.include_router(settings_router)
    app.include_router(chat_router)
    app.include_router(notifications_router)
    app.include_router(speech_router)
