import logging
from typing import Optional, Dict, Tuple

from backend.services.terminal_agent.base import TerminalAgentProvider
from backend.services.terminal_agent.session import TerminalSession

log = logging.getLogger('codex.session')


class SessionManager:
    _sessions: Dict[str, TerminalSession] = {}

    @classmethod
    def get_or_create(
        cls,
        provider: TerminalAgentProvider,
        workspace: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[TerminalSession, bool]:
        key = f"{provider.name}:{workspace}:{model or 'default'}"
        if key in cls._sessions:
            session = cls._sessions[key]
            if session.is_alive():
                return session, False
            session.cleanup()

        session = TerminalSession(provider, workspace, model, session_id)
        cls._sessions[key] = session
        return session, True

    @classmethod
    def cleanup_all(cls) -> None:
        for session in cls._sessions.values():
            session.cleanup()
        cls._sessions.clear()

