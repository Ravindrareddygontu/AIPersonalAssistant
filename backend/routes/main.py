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


IGNORED_FOLDERS = {
    '__pycache__', 'node_modules', 'venv', 'dist', 'build',
    '__pypackages__', '.tox', '.mypy_cache', '.pytest_cache', '.eggs'
}
SEARCH_MAX_RESULTS = 50
SEARCH_MAX_DEPTH = 5
HOME_DIR = os.path.expanduser('~')

def is_ignored_folder(name):
    return (
        name.startswith('.') or
        name in IGNORED_FOLDERS or
        name.endswith('.egg-info')
    )

def build_folder_item(name, browse_path):
    full_path = os.path.join(browse_path, name)
    return {
        'name': name,
        'path': full_path,
        'type': 'directory',
        'display_path': full_path.replace(HOME_DIR, '~')
    }

@main_router.get('/api/browse')
async def browse_directories(request: Request, path: Optional[str] = None):
    url = str(request.url)
    _log_request('GET', url, {'path': path})
    browse_path = os.path.expanduser(path) if path else HOME_DIR
    try:
        if not os.path.isdir(browse_path):
            browse_path = HOME_DIR
        items = [
            build_folder_item(item, browse_path)
            for item in sorted(os.listdir(browse_path))
            if not is_ignored_folder(item) and os.path.isdir(os.path.join(browse_path, item))
        ][:SEARCH_MAX_RESULTS]
        response_data = {'current': browse_path, 'parent': os.path.dirname(browse_path), 'items': items}
        _log_response('GET', url, 200, {'current': browse_path, 'items_count': len(items)})
        return response_data
    except Exception as e:
        response_data = {'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return response_data


@main_router.get('/api/search-folders')
async def search_folders(request: Request, query: str, path: Optional[str] = None):
    url = str(request.url)
    _log_request('GET', url, {'query': query, 'path': path})

    if not query or len(query) < 2:
        return {'items': []}

    search_path = os.path.expanduser(path) if path else HOME_DIR
    query_lower = query.lower()
    results = []

    def search_recursive(current_path, depth):
        if depth > SEARCH_MAX_DEPTH or len(results) >= SEARCH_MAX_RESULTS:
            return
        try:
            for item in os.listdir(current_path):
                if is_ignored_folder(item):
                    continue
                full_path = os.path.join(current_path, item)
                if not os.path.isdir(full_path):
                    continue
                if query_lower in item.lower():
                    results.append({
                        'name': item,
                        'path': full_path,
                        'type': 'directory',
                        'display_path': full_path.replace(HOME_DIR, '~')
                    })
                    if len(results) >= SEARCH_MAX_RESULTS:
                        return
                search_recursive(full_path, depth + 1)
        except (PermissionError, OSError):
            pass

    try:
        search_recursive(search_path, 0)
        response_data = {'items': results}
        _log_response('GET', url, 200, {'items_count': len(results)})
        return response_data
    except Exception as e:
        response_data = {'error': str(e)}
        _log_response('GET', url, 200, response_data)
        return response_data

