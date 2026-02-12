import os
import subprocess
from flask import Blueprint, render_template, request, jsonify
from backend.config import settings

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/api/check-auth')
def check_auth():
    try:
        subprocess.run(['npx', '@augmentcode/auggie', '--help'], capture_output=True, text=True, timeout=30)
        return jsonify({'authenticated': True, 'status': 'ready', 'workspace': settings.workspace})
    except Exception as e:
        return jsonify({'authenticated': False, 'error': str(e)})


@main_bp.route('/api/browse', methods=['GET'])
def browse_directories():
    path = os.path.expanduser(request.args.get('path', os.path.expanduser('~')))
    try:
        if not os.path.isdir(path):
            path = os.path.expanduser('~')
        items = [{'name': item, 'path': os.path.join(path, item), 'type': 'directory'}
                 for item in sorted(os.listdir(path))
                 if os.path.isdir(os.path.join(path, item)) and not item.startswith('.')]
        return jsonify({'current': path, 'parent': os.path.dirname(path), 'items': items[:50]})
    except Exception as e:
        return jsonify({'error': str(e)})

