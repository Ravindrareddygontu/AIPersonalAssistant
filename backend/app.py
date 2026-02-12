import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from backend.routes import register_routes

# Configure logging to show in console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)


def create_app():
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    @app.errorhandler(BrokenPipeError)
    def handle_broken_pipe(e):
        return '', 499

    @app.errorhandler(ConnectionResetError)
    def handle_connection_reset(e):
        return '', 499

    register_routes(app)
    return app


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🤖 AI Chat Application (Powered by Augment Code)")
    print("=" * 60)
    print("Starting server at http://localhost:5000")
    print("=" * 60 + "\n")
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)

