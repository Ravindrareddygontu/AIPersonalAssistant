import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.session import SessionManager
from backend.database import get_chats_collection, check_connection, is_db_available_cached
from backend.services import message_service as msg_svc


def _generate_temp_chat_id():
    return f"temp-{str(uuid.uuid4())[:8]}"

log = logging.getLogger('settings')
settings_router = APIRouter()


# Pydantic models for request validation
class SettingsUpdate(BaseModel):
    workspace: Optional[str] = None
    model: Optional[str] = None
    history_enabled: Optional[bool] = None
    slack_notify: Optional[bool] = None
    slack_webhook_url: Optional[str] = None
    ai_provider: Optional[str] = None
    openai_model: Optional[str] = None


class SessionResetRequest(BaseModel):
    workspace: Optional[str] = None


class ChatUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None


def _log_request(method: str, url: str, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


def _log_response(method: str, url: str, status: int, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[RESPONSE] {method} {url} | Status: {status} | Body: {body_str}")


@settings_router.get('/api/settings')
async def get_settings_endpoint(request: Request):
    url = str(request.url)
    _log_request('GET', url)
    response_data = settings.to_dict()
    _log_response('GET', url, 200, response_data)
    return response_data


@settings_router.post('/api/settings')
async def save_settings(request: Request, data: SettingsUpdate):
    url = str(request.url)
    data_dict = data.model_dump(exclude_none=True)
    _log_request('POST', url, data_dict)

    # Handle workspace
    if data.workspace:
        workspace = os.path.expanduser(data.workspace)
        if os.path.isdir(workspace):
            settings.workspace = workspace
        else:
            response_data = {'status': 'error', 'error': f'Directory not found: {workspace}'}
            _log_response('POST', url, 200, response_data)
            return response_data

    # Handle model
    if data.model:
        old_model = settings.model
        settings.model = data.model
        log.info(f"[SETTINGS] Model change requested: {data.model} (was: {old_model}, now: {settings.model})")

    # Handle history_enabled
    if data.history_enabled is not None:
        old_history = settings.history_enabled
        settings.history_enabled = data.history_enabled
        log.info(f"[SETTINGS] History enabled changed: {old_history} -> {settings.history_enabled}")

    # Handle slack_notify
    if data.slack_notify is not None:
        old_slack_notify = settings.slack_notify
        settings.slack_notify = data.slack_notify
        log.info(f"[SETTINGS] Slack notify changed: {old_slack_notify} -> {settings.slack_notify}")

    # Handle slack_webhook_url
    if data.slack_webhook_url is not None:
        settings.slack_webhook_url = data.slack_webhook_url
        log.info(f"[SETTINGS] Slack webhook URL updated")

    # Handle ai_provider
    if data.ai_provider is not None:
        old_provider = settings.ai_provider
        settings.ai_provider = data.ai_provider
        log.info(f"[SETTINGS] AI provider changed: {old_provider} -> {settings.ai_provider}")

    # Handle openai_model
    if data.openai_model is not None:
        old_model = settings.openai_model
        settings.openai_model = data.openai_model
        log.info(f"[SETTINGS] OpenAI model changed: {old_model} -> {settings.openai_model}")

    response_data = {
        'status': 'success',
        'workspace': settings.workspace,
        'model': settings.model,
        'history_enabled': settings.history_enabled,
        'slack_notify': settings.slack_notify,
        'slack_webhook_url': settings.slack_webhook_url,
        'ai_provider': settings.ai_provider,
        'openai_model': settings.openai_model,
    }
    _log_response('POST', url, 200, response_data)
    return response_data


@settings_router.post('/api/session/reset')
async def reset_session(request: Request, data: Optional[SessionResetRequest] = None):
    url = str(request.url)
    data_dict = data.model_dump() if data else {}
    _log_request('POST', url, data_dict)
    workspace = os.path.expanduser(data.workspace if data and data.workspace else settings.workspace)
    reset_success = SessionManager.reset(workspace)
    if not reset_success:
        response_data = {'status': 'error', 'message': 'Cannot reset: terminal is in use'}
        _log_response('POST', url, 409, response_data)
        return JSONResponse(content=response_data, status_code=409)
    response_data = {'status': 'success', 'message': 'Session reset'}
    _log_response('POST', url, 200, response_data)
    return response_data


@settings_router.get('/api/db-status')
async def get_db_status(request: Request):
    url = str(request.url)
    _log_request('GET', url)
    status = check_connection()
    _log_response('GET', url, 200, status)
    return status


@settings_router.get('/api/chats')
async def list_chats(request: Request):
    url = str(request.url)
    _log_request('GET', url)

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, return empty list
    if chats_collection is None:
        log.warning("[CHATS] MongoDB not available, returning empty chat list")
        _log_response('GET', url, 200, {'chats_count': 0, 'db_available': False})
        return JSONResponse(content=[], headers={'X-DB-Available': 'false'})

    chats = []
    # Sort by created_at descending (newest first, oldest at bottom)
    for doc in chats_collection.find().sort('created_at', -1):
        db_messages = doc.get('messages', [])
        chats.append({
            'id': doc.get('id'),
            'title': doc.get('title', 'Untitled'),
            'created_at': doc.get('created_at'),
            'updated_at': doc.get('updated_at'),
            'message_count': msg_svc.get_message_count(db_messages)
        })
    _log_response('GET', url, 200, {'chats_count': len(chats)})
    return chats


@settings_router.post('/api/chats')
async def create_chat(request: Request):
    url = str(request.url)
    _log_request('POST', url)
    now = datetime.now().isoformat()

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, return a temporary chat
    if chats_collection is None:
        chat_id = _generate_temp_chat_id()
        chat_data = {
            'id': chat_id,
            'title': 'New Chat',
            'created_at': now,
            'updated_at': now,
            'messages': [],
            'workspace': settings.workspace,
            'streaming_status': None,
            'db_available': False  # Flag to indicate DB is not available
        }
        log.warning(f"[CHATS] MongoDB not available, created temp chat: {chat_id}")
        _log_response('POST', url, 200, {**chat_data, 'db_available': False})
        return JSONResponse(content=chat_data, headers={'X-DB-Available': 'false'})

    chat_id = str(uuid.uuid4())[:8]
    chat_data = {
        'id': chat_id,
        'title': 'New Chat',
        'created_at': now,
        'updated_at': now,
        'messages': [],
        'workspace': settings.workspace,
        'streaming_status': None  # None = idle, 'streaming' = active stream, 'pending' = needs resume
    }
    chats_collection.insert_one(chat_data)
    chat_data.pop('_id', None)
    _log_response('POST', url, 200, chat_data)
    return chat_data


@settings_router.delete('/api/chats/clear')
async def clear_all_chats(request: Request):
    url = str(request.url)
    _log_request('DELETE', url)

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, just return success
    if chats_collection is None:
        log.warning("[CHATS] MongoDB not available, skipping clear")
        response_data = {'status': 'cleared', 'db_available': False}
        _log_response('DELETE', url, 200, response_data)
        return JSONResponse(content=response_data, headers={'X-DB-Available': 'false'})

    chats_collection.delete_many({})
    response_data = {'status': 'cleared'}
    _log_response('DELETE', url, 200, response_data)
    return response_data


@settings_router.get('/api/chats/{chat_id}')
async def get_chat(request: Request, chat_id: str):
    url = str(request.url)
    _log_request('GET', url, {'chat_id': chat_id})

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, return empty chat with temp ID
    if chats_collection is None:
        log.warning(f"[CHATS] MongoDB not available, returning empty chat for {chat_id}")
        now = datetime.now().isoformat()
        chat_data = {
            'id': chat_id,
            'title': 'New Chat',
            'created_at': now,
            'updated_at': now,
            'messages': [],
            'db_available': False
        }
        return JSONResponse(
            content=chat_data,
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-DB-Available': 'false'
            }
        )

    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        response_data = {'error': 'Chat not found'}
        _log_response('GET', url, 404, response_data)
        return JSONResponse(content=response_data, status_code=404)
    chat_data.pop('_id', None)

    # Transform DB format to API format for frontend
    db_messages = chat_data.get('messages', [])
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, db_messages)

    _log_response('GET', url, 200, {'chat_id': chat_id, 'messages_count': len(chat_data['messages'])})
    return JSONResponse(
        content=chat_data,
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@settings_router.post('/api/chats/{chat_id}/clear-streaming')
async def clear_streaming_status(chat_id: str):
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, just return success
    if chats_collection is None:
        log.warning(f"[CHATS] MongoDB not available, skipping clear-streaming for {chat_id}")
        return {'status': 'ok', 'db_available': False}

    result = chats_collection.update_one(
        {'id': chat_id},
        {'$set': {'streaming_status': None}}
    )
    if result.matched_count == 0:
        return JSONResponse(content={'error': 'Chat not found'}, status_code=404)
    log.info(f"[CLEAR] Cleared streaming_status for chat {chat_id}")
    return {'status': 'ok'}


@settings_router.put('/api/chats/{chat_id}')
async def update_chat(request: Request, chat_id: str, data: ChatUpdate):
    url = str(request.url)

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, return success (data stays in frontend cache)
    if chats_collection is None:
        log.warning(f"[CHATS] MongoDB not available, skipping save for {chat_id}")
        _log_request('PUT', url, {'chat_id': chat_id, 'messages_count': len(data.messages or [])})
        api_messages = data.messages or []
        now = datetime.now().isoformat()
        chat_data = {
            'id': chat_id,
            'title': data.title or 'New Chat',
            'created_at': now,
            'updated_at': now,
            'messages': api_messages,
            'db_available': False
        }
        # Auto-generate title from first message if still "New Chat"
        if chat_data['title'] == 'New Chat' and api_messages:
            first_msg = api_messages[0]
            if first_msg.get('role') == 'user':
                content = first_msg.get('content', '')
                chat_data['title'] = content[:50] + ('...' if len(content) > 50 else '')
        _log_response('PUT', url, 200, {'chat_id': chat_id, 'messages_count': len(api_messages), 'db_available': False})
        return JSONResponse(content=chat_data, headers={'X-DB-Available': 'false'})

    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        response_data = {'error': 'Chat not found'}
        _log_response('PUT', url, 404, response_data)
        return JSONResponse(content=response_data, status_code=404)

    data_dict = data.model_dump(exclude_none=True)
    _log_request('PUT', url, {'chat_id': chat_id, 'messages_count': len(data.messages or [])})

    api_messages = data.messages or []
    msg_count = len(api_messages)
    roles = [m.get('role') for m in api_messages]
    log.info(f"[SAVE] PUT /api/chats/{chat_id} - {msg_count} API messages, roles: {roles}")

    if data.title is not None:
        chat_data['title'] = data.title

    if data.messages is not None:
        db_messages = msg_svc.api_to_db_format(chat_id, api_messages)
        chat_data['messages'] = db_messages
        log.info(f"[SAVE] Converted to {len(db_messages)} Q&A pairs")

    # Auto-generate title from first question if still "New Chat"
    if chat_data['title'] == 'New Chat' and chat_data.get('messages'):
        first_pair = chat_data['messages'][0]
        if first_pair.get('question'):
            content = first_pair['question']
            chat_data['title'] = content[:50] + ('...' if len(content) > 50 else '')

    chat_data['updated_at'] = datetime.now().isoformat()
    chats_collection.update_one({'id': chat_id}, {'$set': chat_data})

    log.info(f"[SAVE] Saved chat {chat_id} with {len(chat_data.get('messages', []))} Q&A pairs")

    chat_data.pop('_id', None)
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, chat_data['messages'])
    _log_response('PUT', url, 200, {'chat_id': chat_id, 'messages_count': len(chat_data['messages'])})
    return chat_data


@settings_router.delete('/api/chats/{chat_id}')
async def delete_chat(request: Request, chat_id: str):
    url = str(request.url)
    _log_request('DELETE', url, {'chat_id': chat_id})

    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        chats_collection = None
    else:
        chats_collection = get_chats_collection()

    # If MongoDB is not available, return success
    if chats_collection is None:
        log.warning(f"[CHATS] MongoDB not available, skipping delete for {chat_id}")
        response_data = {'status': 'deleted', 'id': chat_id, 'db_available': False}
        _log_response('DELETE', url, 200, response_data)
        return JSONResponse(content=response_data, headers={'X-DB-Available': 'false'})

    result = chats_collection.delete_one({'id': chat_id})
    if result.deleted_count == 0:
        response_data = {'error': 'Chat not found'}
        _log_response('DELETE', url, 404, response_data)
        return JSONResponse(content=response_data, status_code=404)
    response_data = {'status': 'deleted', 'id': chat_id}
    _log_response('DELETE', url, 200, response_data)
    return response_data




