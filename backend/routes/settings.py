import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from backend.config import settings, CHATS_DIR
from backend.session import SessionManager

settings_bp = Blueprint('settings', __name__)


def get_chat_filepath(chat_id):
    return os.path.join(CHATS_DIR, f'{chat_id}.json')


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
    chats = []
    for filename in os.listdir(CHATS_DIR):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(CHATS_DIR, filename), 'r') as f:
                    d = json.load(f)
                    chats.append({'id': d.get('id'), 'title': d.get('title', 'Untitled'),
                                  'created_at': d.get('created_at'), 'updated_at': d.get('updated_at'),
                                  'message_count': len(d.get('messages', []))})
            except:
                pass
    chats.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return jsonify(chats)


@settings_bp.route('/api/chats', methods=['POST'])
def create_chat():
    import uuid
    chat_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    chat_data = {'id': chat_id, 'title': 'New Chat', 'created_at': now,
                 'updated_at': now, 'messages': [], 'workspace': settings.workspace}
    with open(get_chat_filepath(chat_id), 'w') as f:
        json.dump(chat_data, f, indent=2)
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404
    with open(filepath, 'r') as f:
        return jsonify(json.load(f))


@settings_bp.route('/api/chats/<chat_id>', methods=['PUT'])
def update_chat(chat_id):
    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404
    with open(filepath, 'r') as f:
        chat_data = json.load(f)
    data = request.json
    if 'title' in data:
        chat_data['title'] = data['title']
    if 'messages' in data:
        chat_data['messages'] = data['messages']
    if chat_data['title'] == 'New Chat' and chat_data['messages']:
        for msg in chat_data['messages']:
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                chat_data['title'] = content[:50] + ('...' if len(content) > 50 else '')
                break
    chat_data['updated_at'] = datetime.now().isoformat()
    with open(filepath, 'w') as f:
        json.dump(chat_data, f, indent=2)
    return jsonify(chat_data)


@settings_bp.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404
    os.remove(filepath)
    return jsonify({'status': 'deleted', 'id': chat_id})


@settings_bp.route('/api/chats/clear', methods=['DELETE'])
def clear_all_chats():
    for f in os.listdir(CHATS_DIR):
        if f.endswith('.json'):
            os.remove(os.path.join(CHATS_DIR, f))
    return jsonify({'status': 'cleared'})

