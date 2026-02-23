import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
from dataclasses import dataclass, asdict
from threading import Lock

log = logging.getLogger('session_manager')

SESSIONS_DIR = os.path.expanduser('~/.ai-chat-app/sessions')
AUGMENT_SESSIONS_DIR = os.path.expanduser('~/.augment/sessions')


@dataclass
class SessionInfo:
    session_id: str
    workspace: str
    provider: str
    model: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SessionManager:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._sessions: Dict[str, SessionInfo] = {}
        self._file_lock = Lock()
        self._ensure_dir()
        self._load_sessions()

    def _ensure_dir(self):
        Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

    def _sessions_file(self) -> Path:
        return Path(SESSIONS_DIR) / 'sessions.json'

    def _load_sessions(self):
        try:
            if self._sessions_file().exists():
                with open(self._sessions_file(), 'r') as f:
                    data = json.load(f)
                    for key, info in data.items():
                        self._sessions[key] = SessionInfo(**info)
                log.info(f"Loaded {len(self._sessions)} sessions from disk")
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"Failed to load sessions: {e}")

    def _save_sessions(self):
        with self._file_lock:
            try:
                data = {k: asdict(v) for k, v in self._sessions.items()}
                with open(self._sessions_file(), 'w') as f:
                    json.dump(data, f, indent=2)
            except OSError as e:
                log.error(f"Failed to save sessions: {e}")

    def _make_key(self, provider: str, workspace: str, model: Optional[str] = None) -> str:
        return f"{provider}:{workspace}:{model or 'default'}"

    def store_session(self, provider: str, workspace: str, session_id: str, model: Optional[str] = None):
        key = self._make_key(provider, workspace, model)
        now = datetime.now().isoformat()
        existing = self._sessions.get(key)
        if existing and existing.session_id == session_id:
            existing.updated_at = now
        else:
            self._sessions[key] = SessionInfo(
                session_id=session_id,
                workspace=workspace,
                provider=provider,
                model=model,
                created_at=now,
                updated_at=now,
            )
            log.info(f"Stored session {session_id} for {provider}:{workspace}")
        self._save_sessions()

    def get_session(self, provider: str, workspace: str, model: Optional[str] = None) -> Optional[str]:
        key = self._make_key(provider, workspace, model)
        log.info(f"[GET_SESSION] provider={provider}, workspace={workspace}, model={model}, key={key}")
        info = self._sessions.get(key)
        if info:
            log.info(f"[GET_SESSION] Found in cache: {info.session_id}")
            if provider == 'auggie' and not self._auggie_session_exists(info.session_id):
                log.info(f"[GET_SESSION] Auggie session {info.session_id} no longer exists on disk")
                self.clear_session(provider, workspace, model)
                return None
            return info.session_id
        log.info(f"[GET_SESSION] Not in cache, searching filesystem...")
        if provider == 'auggie':
            session_id = self._find_auggie_session(workspace)
            log.info(f"[GET_SESSION] _find_auggie_session returned: {session_id}")
            if session_id:
                self.store_session(provider, workspace, session_id, model)
            return session_id
        return None

    def clear_session(self, provider: str, workspace: str, model: Optional[str] = None):
        key = self._make_key(provider, workspace, model)
        if key in self._sessions:
            del self._sessions[key]
            log.info(f"Cleared session for {provider}:{workspace}")
            self._save_sessions()

    def session_exists(self, provider: str, session_id: str) -> bool:
        if provider == 'auggie':
            return self._auggie_session_exists(session_id)
        return any(s.session_id == session_id for s in self._sessions.values())

    def _auggie_session_exists(self, session_id: str) -> bool:
        if not session_id:
            return False
        session_file = Path(AUGMENT_SESSIONS_DIR) / f"{session_id}.json"
        return session_file.exists()

    def _find_auggie_session(self, workspace: str) -> Optional[str]:
        sessions_dir = Path(AUGMENT_SESSIONS_DIR)
        if not sessions_dir.exists():
            return None
        workspace = os.path.normpath(workspace)
        best_session = None
        best_modified = None
        for session_file in sessions_dir.glob('*.json'):
            try:
                stat = session_file.stat()
                modified_time = datetime.fromtimestamp(stat.st_mtime)
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
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return best_session


session_manager = SessionManager()

