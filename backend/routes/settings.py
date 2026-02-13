import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from backend.config import settings
from backend.session import SessionManager
from backend.database import get_chats_collection
from backend.services import message_service as msg_svc

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify(settings.to_dict())


@settings_bp.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    if data.get('workspace'):
        workspace = os.path.expanduser(data['workspace'])
        if os.path.isdir(workspace):
            settings.workspace = workspace
            return jsonify({'status': 'success', 'workspace': workspace})
        return jsonify({'status': 'error', 'error': f'Directory not found: {workspace}'})
    return jsonify({'status': 'success'})


@settings_bp.route('/api/session/reset', methods=['POST'])
def reset_session():
    data = request.json or {}
    workspace = os.path.expanduser(data.get('workspace', settings.workspace))
    SessionManager.reset(workspace)
    return jsonify({'status': 'success', 'message': 'Session reset'})


@settings_bp.route('/api/chats', methods=['GET'])
def list_chats():
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
    return jsonify(chats)


@settings_bp.route('/api/chats', methods=['POST'])
def create_chat():
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
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    chats_collection = get_chats_collection()
    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        return jsonify({'error': 'Chat not found'}), 404
    chat_data.pop('_id', None)

    # Transform DB format to API format for frontend
    db_messages = chat_data.get('messages', [])
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, db_messages)

    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['PUT'])
def update_chat(chat_id):
    chats_collection = get_chats_collection()
    chat_data = chats_collection.find_one({'id': chat_id})
    if not chat_data:
        return jsonify({'error': 'Chat not found'}), 404

    data = request.json

    # Log incoming data for debugging
    api_messages = data.get('messages', [])
    msg_count = len(api_messages)
    roles = [m.get('role') for m in api_messages]
    print(f"[SAVE] PUT /api/chats/{chat_id} - {msg_count} API messages, roles: {roles}", flush=True)

    if 'title' in data:
        chat_data['title'] = data['title']

    if 'messages' in data:
        # Convert API format to DB format for storage
        db_messages = msg_svc.api_to_db_format(chat_id, api_messages)
        chat_data['messages'] = db_messages
        print(f"[SAVE] Converted to {len(db_messages)} Q&A pairs", flush=True)

    # Auto-generate title from first question if still "New Chat"
    if chat_data['title'] == 'New Chat' and chat_data.get('messages'):
        first_pair = chat_data['messages'][0]
        if first_pair.get('question'):
            content = first_pair['question']
            chat_data['title'] = content[:50] + ('...' if len(content) > 50 else '')

    chat_data['updated_at'] = datetime.now().isoformat()

    chats_collection.update_one({'id': chat_id}, {'$set': chat_data})

    print(f"[SAVE] Saved chat {chat_id} with {len(chat_data.get('messages', []))} Q&A pairs", flush=True)

    # Return API format for frontend
    chat_data.pop('_id', None)
    chat_data['messages'] = msg_svc.db_to_api_format(chat_id, chat_data['messages'])
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    chats_collection = get_chats_collection()
    result = chats_collection.delete_one({'id': chat_id})
    if result.deleted_count == 0:
        return jsonify({'error': 'Chat not found'}), 404
    return jsonify({'status': 'deleted', 'id': chat_id})


@settings_bp.route('/api/chats/clear', methods=['DELETE'])
def clear_all_chats():
    chats_collection = get_chats_collection()
    chats_collection.delete_many({})
    return jsonify({'status': 'cleared'})

