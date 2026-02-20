import logging
from abc import ABC, abstractmethod
from typing import Optional
from backend.database import is_db_available_cached

log = logging.getLogger('repository.base')


class BaseRepository(ABC):

    def __init__(self):
        self._collection = None
        self._db_available: Optional[bool] = None
        if not is_db_available_cached():
            self._db_available = False

    @abstractmethod
    def _get_collection(self):
        pass

    @property
    def collection(self):
        if self._db_available is False:
            return None
        if self._collection is None:
            self._collection = self._get_collection()
            self._db_available = self._collection is not None
        return self._collection

    @property
    def is_db_available(self) -> bool:
        if self._db_available is None:
            if not is_db_available_cached():
                self._db_available = False
                return False
            _ = self.collection
        return self._db_available

    @staticmethod
    def generate_title(text: str, max_length: int = 50) -> str:
        if not text:
            return "Untitled"
        if len(text) > max_length:
            return text[:max_length] + '...'
        return text

