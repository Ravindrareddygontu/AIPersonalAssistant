import os
import json
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from backend.config import settings
from backend.session import SessionManager
from backend.database import get_chats_collection
from backend.services import message_service as msg_svc

log = logging.getLogger('settings')
settings_bp = Blueprint('settings', __name__)


def _log_request(method, url, body=None):
    """Log incoming request details"""
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


def _log_response(method, url, status, body=None):
    """Log outgoing response details"""
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[RESPONSE] {method} {url} | Status: {status} | Body: {body_str}")


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    url = request.url
    _log_request('GET', url)
    response_data = settings.to_dict()
    _log_response('GET', url, 200, response_data)
    return jsonify(response_data)


@settings_bp.route('/api/settings', methods=['POST'])
def save_settings():
    url = request.url
    data = request.json
    _log_request('POST', url, data)

    # Handle workspace
    if data.get('workspace'):
        workspace = os.path.expanduser(data['workspace'])
        if os.path.isdir(workspace):
            settings.workspace = workspace
        else:
            response_data = {'status': 'error', 'error': f'Directory not found: {workspace}'}
            _log_response('POST', url, 200, response_data)
            return jsonify(response_data)

    # Handle model
    if data.get('model'):
        old_model = settings.model
        settings.model = data['model']
        log.info(f"[SETTINGS] Model change requested: {data['model']} (was: {old_model}, now: {settings.model})")

    # Handle history_enabled
    if 'history_enabled' in data:
        old_history = settings.history_enabled
        settings.history_enabled = data['history_enabled']
        log.info(f"[SETTINGS] History enabled changed: {old_history} -> {settings.history_enabled}")

    # Handle slack_notify
    if 'slack_notify' in data:
        old_slack_notify = settings.slack_notify
        settings.slack_notify = data['slack_notify']
        log.info(f"[SETTINGS] Slack notify changed: {old_slack_notify} -> {settings.slack_notify}")

    # Handle slack_webhook_url
    if 'slack_webhook_url' in data:
        settings.slack_webhook_url = data['slack_webhook_url']
        log.info(f"[SETTINGS] Slack webhook URL updated")

    response_data = {
        'status': 'success',
        'workspace': settings.workspace,
        'model': settings.model,
        'history_enabled': settings.history_enabled,
        'slack_notify': settings.slack_notify,
        'slack_webhook_url': settings.slack_webhook_url
    }
    _log_response('POST', url, 200, response_data)
    return jsonify(response_data)


@settings_bp.route('/api/session/reset', methods=['POST'])
def reset_session():
    url = request.url
    data = request.json or {}
    _log_request('POST', url, data)
    workspace = os.path.expanduser(data.get('workspace', settings.workspace))
    reset_success = SessionManager.reset(workspace)
    if not reset_success:
        response_data = {'status': 'error', 'message': 'Cannot reset: terminal is in use'}
        _log_response('POST', url, 409, response_data)
        return jsonify(response_data), 409
    response_data = {'status': 'success', 'message': 'Session reset'}
    _log_response('POST', url, 200, response_data)
    return jsonify(response_data)


@settings_bp.route('/api/chats', methods=['GET'])
def list_chats():
    url = request.url
    _log_request('GET', url)
    chats_collection = get_chats_collection()
    chats = []
    for doc in chats_collection.find().sort('updated_at', -1):
        db_messages = doc.get('messages', [])
        chats.append({
            'id': doc.get('id'),
            'title': doc.get('title', 'Untitled'),
            'created_at': doc.get('created_at'),
            'updated_at': doc.get('updated_at'),
            'message_count': msg_svc.get_message_count(db_messages)
        })
    _log_response('GET', url, 200, {'chats_count': len(chats)})
    return jsonify(chats)


@settings_bp.route('/api/chats', methods=['POST'])
def create_chat():
    url = request.url
    _log_request('POST', url)
    chats_collection = get_chats_collection()
    chat_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    chat_data = {
        'id': chat_id,
        'title': 'New Chat',
        'created_at': now,
        'updated_at': now,
        'messages': [],
        'workspace': settings.workspace
    }
    chats_collection.insert_one(chat_data)
    # Remove MongoDB's _id field for JSON response
    chat_data.pop('_id', None)
    _log_response('POST', url, 200, chat_data)
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    url = request.url
    _log_request('GET', url, {'chat_id': chat_id})
    chats_collection = get_chats_collection()
    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        response_data = {'error': 'Chat not found'}
        _log_response('GET', url, 404, response_data)
        return jsonify(response_data), 404
    chat_data.pop('_id', None)

    # Transform DB format to API format for frontend
    db_messages = chat_data.get('messages', [])
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, db_messages)

    _log_response('GET', url, 200, {'chat_id': chat_id, 'messages_count': len(chat_data['messages'])})
    response = jsonify(chat_data)
    # Prevent browser caching to ensure fresh data on refresh
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@settings_bp.route('/api/chats/<chat_id>', methods=['PUT'])
def update_chat(chat_id):
    url = request.url
    chats_collection = get_chats_collection()
    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        response_data = {'error': 'Chat not found'}
        _log_response('PUT', url, 404, response_data)
        return jsonify(response_data), 404

    data = request.json
    _log_request('PUT', url, {'chat_id': chat_id, 'messages_count': len(data.get('messages', []))})

    # Log incoming data for debugging
    api_messages = data.get('messages', [])
    msg_count = len(api_messages)
    roles = [m.get('role') for m in api_messages]
    log.info(f"[SAVE] PUT /api/chats/{chat_id} - {msg_count} API messages, roles: {roles}")

    if 'title' in data:
        chat_data['title'] = data['title']

    if 'messages' in data:
        # Convert API format to DB format for storage
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

    # Return API format for frontend
    chat_data.pop('_id', None)
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, chat_data['messages'])
    _log_response('PUT', url, 200, {'chat_id': chat_id, 'messages_count': len(chat_data['messages'])})
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    url = request.url
    _log_request('DELETE', url, {'chat_id': chat_id})
    chats_collection = get_chats_collection()
    result = chats_collection.delete_one({'id': chat_id})
    if result.deleted_count == 0:
        response_data = {'error': 'Chat not found'}
        _log_response('DELETE', url, 404, response_data)
        return jsonify(response_data), 404
    response_data = {'status': 'deleted', 'id': chat_id}
    _log_response('DELETE', url, 200, response_data)
    return jsonify(response_data)


@settings_bp.route('/api/chats/clear', methods=['DELETE'])
def clear_all_chats():
    url = request.url
    _log_request('DELETE', url)
    chats_collection = get_chats_collection()
    chats_collection.delete_many({})
    response_data = {'status': 'cleared'}
    _log_response('DELETE', url, 200, response_data)
    return jsonify(response_data)

