import os
import json
import logging
import subprocess
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.config import settings

log = logging.getLogger('main')
main_router = APIRouter()

# Templates will be configured when the app starts
templates: Optional[Jinja2Templates] = None


def set_templates(tmpl: Jinja2Templates):
    global templates
    templates = tmpl


def _log_request(method: str, url: str, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


def _log_response(method: str, url: str, status: int, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[RESPONSE] {method} {url} | Status: {status} | Body: {body_str}")


@main_router.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@main_router.get('/api/check-auth')
async def check_auth(request: Request):
    url = str(request.url)
    _log_request('GET', url)
    try:
        subprocess.run(['npx', '@augmentcode/auggie', '--help'], capture_output=True, text=True, timeout=30)
        response_data = {'authenticated': True, 'status': 'ready', 'workspace': settings.workspace}
        _log_response('GET', url, 200, response_data)
        return response_data
    except Exception as e:
        response_data = {'authenticated': False, 'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return response_data


@main_router.get('/api/browse')
async def browse_directories(request: Request, path: Optional[str] = None):
    url = str(request.url)
    _log_request('GET', url, {'path': path})
    browse_path = os.path.expanduser(path if path else os.path.expanduser('~'))
    try:
        if not os.path.isdir(browse_path):
            browse_path = os.path.expanduser('~')
        items = [{'name': item, 'path': os.path.join(browse_path, item), 'type': 'directory'}
                 for item in sorted(os.listdir(browse_path))
                 if os.path.isdir(os.path.join(browse_path, item)) and not item.startswith('.')]
        response_data = {'current': browse_path, 'parent': os.path.dirname(browse_path), 'items': items[:50]}
        _log_response('GET', url, 200, {'current': browse_path, 'items_count': len(items[:50])})
        return response_data
    except Exception as e:
        response_data = {'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return response_data

