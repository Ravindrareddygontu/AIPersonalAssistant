import logging
from typing import Optional, Tuple

from backend.session import BaseSessionManager
from backend.services.terminal_agent.base import TerminalAgentProvider
from backend.services.terminal_agent.session import TerminalSession

log = logging.getLogger('codex.session')


class SessionManager(BaseSessionManager[TerminalSession]):
    _sessions = {}

    @classmethod
    def _get_session_key(cls, provider: TerminalAgentProvider, workspace: str, model: Optional[str] = None) -> str:
        return f"{provider.name}:{workspace}:{model or 'default'}"

    @classmethod
    def _create_session(cls, provider: TerminalAgentProvider, workspace: str, model: Optional[str] = None, session_id: Optional[str] = None) -> TerminalSession:
        return TerminalSession(provider, workspace, model, session_id)

    @classmethod
    def get_or_create(
        cls,
        provider: TerminalAgentProvider,
        workspace: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[TerminalSession, bool]:
        key = cls._get_session_key(provider, workspace, model)
        with cls._lock:
            existing = cls._get_existing_session(key)
            if existing:
                return existing, False

            session = cls._create_session(provider, workspace, model, session_id)
            cls._sessions[key] = session
            return session, True

