import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, Tuple, TypeVar, Generic

from backend.session.base import BasePtySession

log = logging.getLogger('session.manager')

S = TypeVar('S', bound=BasePtySession)


class BaseSessionManager(ABC, Generic[S]):
    _sessions: Dict[str, S] = {}
    _lock = threading.Lock()

    @classmethod
    @abstractmethod
    def _get_session_key(cls, *args, **kwargs) -> str:
        pass

    @classmethod
    @abstractmethod
    def _create_session(cls, *args, **kwargs) -> S:
        pass

    @classmethod
    def _get_existing_session(cls, key: str) -> S | None:
        if key in cls._sessions:
            session = cls._sessions[key]
            if session.is_alive():
                return session
            log.info(f"Session {key} is dead, cleaning up")
            session.cleanup()
            del cls._sessions[key]
        return None

    @classmethod
    def cleanup_all(cls) -> None:
        with cls._lock:
            for session in cls._sessions.values():
                session.cleanup()
            cls._sessions.clear()
            log.info("Cleaned up all sessions")

