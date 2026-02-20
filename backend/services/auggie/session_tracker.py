import os
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

log = logging.getLogger('auggie.session')

AUGMENT_SESSIONS_DIR = os.path.expanduser('~/.augment/sessions')


def get_latest_session_for_workspace(workspace: str, after_time: datetime = None) -> Optional[str]:
    sessions_dir = Path(AUGMENT_SESSIONS_DIR)
    if not sessions_dir.exists():
        log.warning(f"Augment sessions directory not found: {sessions_dir}")
        return None

    workspace = os.path.normpath(workspace)
    best_session = None
    best_modified = None

    for session_file in sessions_dir.glob('*.json'):
        try:
            stat = session_file.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime)

            if after_time and modified_time < after_time:
                continue

            with open(session_file, 'r') as f:
                data = json.load(f)

            chat_history = data.get('chatHistory', [])
            if not chat_history:
                continue

            first_exchange = chat_history[0]
            exchange = first_exchange.get('exchange', {})
            request_nodes = exchange.get('request_nodes', [])

            for node in request_nodes:
                if node.get('type') == 4:
                    ide_state = node.get('ide_state_node', {})
                    workspace_folders = ide_state.get('workspace_folders', [])
                    for folder in workspace_folders:
                        folder_root = folder.get('folder_root', '')
                        if os.path.normpath(folder_root) == workspace:
                            if best_modified is None or modified_time > best_modified:
                                best_session = data.get('sessionId')
                                best_modified = modified_time
                    break

        except (json.JSONDecodeError, KeyError, OSError) as e:
            log.debug(f"Error reading session file {session_file}: {e}")
            continue

    if best_session:
        log.info(f"Found Auggie session {best_session} for workspace {workspace}")
    return best_session


def session_exists(session_id: str) -> bool:
    if not session_id:
        return False
    session_file = Path(AUGMENT_SESSIONS_DIR) / f"{session_id}.json"
    return session_file.exists()


def get_session_workspace(session_id: str) -> Optional[str]:
    if not session_id:
        return None
    
    session_file = Path(AUGMENT_SESSIONS_DIR) / f"{session_id}.json"
    if not session_file.exists():
        return None

    try:
        with open(session_file, 'r') as f:
            data = json.load(f)

        chat_history = data.get('chatHistory', [])
        if not chat_history:
            return None

        first_exchange = chat_history[0]
        exchange = first_exchange.get('exchange', {})
        request_nodes = exchange.get('request_nodes', [])

        for node in request_nodes:
            if node.get('type') == 4:
                ide_state = node.get('ide_state_node', {})
                workspace_folders = ide_state.get('workspace_folders', [])
                if workspace_folders:
                    return workspace_folders[0].get('folder_root')
        return None

    except (json.JSONDecodeError, KeyError, OSError) as e:
        log.debug(f"Error reading session file {session_file}: {e}")
        return None

