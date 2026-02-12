from backend.routes.main import main_bp
from backend.routes.settings import settings_bp
from backend.routes.chat import chat_bp


def register_routes(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(chat_bp)

