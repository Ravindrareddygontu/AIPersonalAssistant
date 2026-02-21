import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

from .locking import file_lock
from .index import StorageIndex

log = logging.getLogger('storage.file_storage')


class FileStorage:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._indexes: Dict[str, StorageIndex] = {}
        os.makedirs(base_dir, exist_ok=True)
        log.info(f"FileStorage initialized at {base_dir}")

    def get_index(self, collection: str) -> StorageIndex:
        if collection not in self._indexes:
            self._indexes[collection] = StorageIndex(self.base_dir, collection)
            self._indexes[collection].load()
        return self._indexes[collection]

    def get_file_path(self, collection: str, doc_id: str, created_at: str = None) -> str:
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except (ValueError, TypeError) as e:
                log.warning(f"Invalid created_at format '{created_at}': {e}, using current time")
                dt = datetime.utcnow()
        else:
            dt = datetime.utcnow()

        year = dt.strftime('%Y')
        month = dt.strftime('%m')
        day = dt.strftime('%d')

        safe_doc_id = self._sanitize_doc_id(doc_id)
        return os.path.join(
            self.base_dir, collection, year, month, day, f"{safe_doc_id}.json"
        )

    def _sanitize_doc_id(self, doc_id: str) -> str:
        if not doc_id:
            raise ValueError("doc_id cannot be empty")
        safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
        sanitized = ''.join(c if c in safe_chars else '_' for c in str(doc_id))
        return sanitized[:100]

    def _ensure_dir(self, path: str) -> None:
        dir_path = os.path.dirname(path)
        os.makedirs(dir_path, exist_ok=True)

    def read(self, collection: str, doc_id: str) -> Optional[dict]:
        if not doc_id:
            log.warning("read called with empty doc_id")
            return None

        index = self.get_index(collection)
        path = index.get(doc_id)
        if not path or not os.path.exists(path):
            return None

        try:
            with file_lock(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except json.JSONDecodeError as e:
            log.error(f"Corrupted JSON in {path}: {e}")
            return None
        except (IOError, OSError) as e:
            log.error(f"IO error reading {path}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error reading {path}: {e}")
            return None

    def write(self, collection: str, doc_id: str, data: dict, created_at: str = None) -> bool:
        if not doc_id:
            log.error("write called with empty doc_id")
            return False
        if not isinstance(data, dict):
            log.error(f"write called with non-dict data: {type(data)}")
            return False

        path = self.get_file_path(collection, doc_id, created_at or data.get('created_at'))
        self._ensure_dir(path)

        try:
            with file_lock(path):
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)

            index = self.get_index(collection)
            index.set(doc_id, path, data.get('created_at'), data.get('updated_at'))
            index.save()
            log.debug(f"Wrote document {doc_id} to {path}")
            return True
        except (IOError, OSError) as e:
            log.error(f"IO error writing {path}: {e}")
            return False
        except Exception as e:
            log.error(f"Unexpected error writing {path}: {e}")
            return False

    def delete(self, collection: str, doc_id: str) -> bool:
        index = self.get_index(collection)
        path = index.get(doc_id)
        if not path:
            return False

        try:
            if os.path.exists(path):
                with file_lock(path):
                    os.remove(path)
            index.delete(doc_id)
            index.save()
            return True
        except Exception as e:
            log.error(f"Failed to delete {path}: {e}")
            return False

    def list_all(self, collection: str) -> list:
        index = self.get_index(collection)
        result = []
        for doc_id in index.all_ids():
            doc = self.read(collection, doc_id)
            if doc:
                result.append(doc)
        return result

    def save_indexes(self) -> None:
        for index in self._indexes.values():
            index.save()

