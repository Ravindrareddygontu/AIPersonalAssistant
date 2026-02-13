import os
import json
import logging
import subprocess
from flask import Blueprint, render_template, request, jsonify
from backend.config import settings

log = logging.getLogger('main')
main_bp = Blueprint('main', __name__)


def _log_request(method, url, body=None):
    """Log incoming request details"""
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


def _log_response(method, url, status, body=None):
    """Log outgoing response details"""
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[RESPONSE] {method} {url} | Status: {status} | Body: {body_str}")


@main_bp.route('/')
def index():
    return render_template('index.html')


@main_bp.route('/api/check-auth')
def check_auth():
    url = request.url
    _log_request('GET', url)
    try:
        subprocess.run(['npx', '@augmentcode/auggie', '--help'], capture_output=True, text=True, timeout=30)
        response_data = {'authenticated': True, 'status': 'ready', 'workspace': settings.workspace}
        _log_response('GET', url, 200, response_data)
        return jsonify(response_data)
    except Exception as e:
        response_data = {'authenticated': False, 'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return jsonify(response_data)


@main_bp.route('/api/browse', methods=['GET'])
def browse_directories():
    url = request.url
    _log_request('GET', url, {'path': request.args.get('path')})
    path = os.path.expanduser(request.args.get('path', os.path.expanduser('~')))
    try:
        if not os.path.isdir(path):
            path = os.path.expanduser('~')
        items = [{'name': item, 'path': os.path.join(path, item), 'type': 'directory'}
                 for item in sorted(os.listdir(path))
                 if os.path.isdir(os.path.join(path, item)) and not item.startswith('.')]
        response_data = {'current': path, 'parent': os.path.dirname(path), 'items': items[:50]}
        _log_response('GET', url, 200, {'current': path, 'items_count': len(items[:50])})
        return jsonify(response_data)
    except Exception as e:
        response_data = {'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return jsonify(response_data)

