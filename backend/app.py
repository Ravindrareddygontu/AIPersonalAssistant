"""AI Chat Application - FastAPI backend."""
import os
import sys
import logging
from contextlib import asynccontextmanager

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from backend.routes import register_routes, set_templates

# Configure logging to show in console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)

log = logging.getLogger('app')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    log.info("🚀 AI Chat Application starting...")
    yield
    log.info("👋 AI Chat Application shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    app = FastAPI(
        title="AI Chat Application",
        description="Powered by Augment Code",
        version="1.0.0",
        lifespan=lifespan
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure templates
    templates = Jinja2Templates(directory=template_dir)
    set_templates(templates)

    # Mount static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Register all routes
    register_routes(app)

    # Exception handlers
    @app.exception_handler(BrokenPipeError)
    async def handle_broken_pipe(request: Request, exc: BrokenPipeError):
        return Response(status_code=499)

    @app.exception_handler(ConnectionResetError)
    async def handle_connection_reset(request: Request, exc: ConnectionResetError):
        return Response(status_code=499)

    return app


# Create the app instance for uvicorn
app = create_app()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🤖 AI Chat Application (Powered by Augment Code)")
    print("=" * 60)
    print("Starting server at http://localhost:5000")
    print("=" * 60 + "\n")

    # Run the main app with uvicorn
    is_production = os.environ.get('FLASK_ENV') == 'production'
    uvicorn.run(
        "backend.app:app",
        host='0.0.0.0',
        port=5000,
        reload=not is_production,
        log_level='info'
    )

