
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

# Configure logging with colored errors for all loggers including uvicorn
class ColoredFormatter(logging.Formatter):
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

    def format(self, record):
        msg = super().format(record)
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{msg}{self.RESET}"
        elif record.levelno >= logging.WARNING:
            return f"{self.YELLOW}{msg}{self.RESET}"
        return msg

colored_formatter = ColoredFormatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(colored_formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [handler]

for logger_name in ['uvicorn', 'uvicorn.error', 'uvicorn.access']:
    uv_logger = logging.getLogger(logger_name)
    uv_logger.handlers = [handler]
    uv_logger.propagate = False

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

log = logging.getLogger('app')


def _register_terminal_agents():
    from backend.services.auggie import register_auggie_provider
    from backend.services.codex import register_codex_provider
    register_auggie_provider()
    register_codex_provider()
    log.info("✓ Terminal agent providers registered (auggie, codex)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 AI Chat Application starting...")
    _register_terminal_agents()
    yield
    log.info("👋 AI Chat Application shutting down...")


def create_app() -> FastAPI:
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
    async def handle_broken_pipe(_request: Request, _exc: BrokenPipeError):
        return Response(status_code=499)

    @app.exception_handler(ConnectionResetError)
    async def handle_connection_reset(_request: Request, _exc: ConnectionResetError):
        return Response(status_code=499)

    return app


# Create the app instance for uvicorn
app = create_app()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🤖 AI Chat Application (Powered by Augment Code)")
    print("=" * 60)
    print("Starting server at http://localhost:5001")
    print("=" * 60 + "\n")

    # Run the main app with uvicorn
    # Default to no reload unless DEV_RELOAD=true (reload causes high CPU)
    enable_reload = os.environ.get('DEV_RELOAD', '').lower() == 'true'
    uvicorn.run(
        "backend.app:app",
        host='0.0.0.0',
        port=5001,
        reload=enable_reload,
        log_level='info'
    )

