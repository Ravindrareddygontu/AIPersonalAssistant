import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional, Any

from .locking import file_lock

log = logging.getLogger('storage.index')


class StorageIndex:
    def __init__(self, base_dir: str, collection: str):
        self.base_dir = base_dir
        self.collection = collection
        self.collection_dir = os.path.join(base_dir, collection)
        self.index_path = os.path.join(self.collection_dir, '_index.json')
        self._index: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._dirty = False

    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.index_path):
                try:
                    with file_lock(self.index_path):
                        with open(self.index_path, 'r') as f:
                            self._index = json.load(f)
                    log.info(f"Loaded index for {self.collection}: {len(self._index)} entries")
                except Exception as e:
                    log.warning(f"Failed to load index for {self.collection}: {e}, rebuilding")
                    self._rebuild()
            else:
                self._rebuild()

    def _rebuild(self) -> None:
        self._index = {}
        if not os.path.exists(self.collection_dir):
            os.makedirs(self.collection_dir, exist_ok=True)
            return

        for year in os.listdir(self.collection_dir):
            year_path = os.path.join(self.collection_dir, year)
            if not os.path.isdir(year_path) or year.startswith('_'):
                continue
            for month in os.listdir(year_path):
                month_path = os.path.join(year_path, month)
                if not os.path.isdir(month_path):
                    continue
                for day in os.listdir(month_path):
                    day_path = os.path.join(month_path, day)
                    if not os.path.isdir(day_path):
                        continue
                    for filename in os.listdir(day_path):
                        if filename.endswith('.json'):
                            file_path = os.path.join(day_path, filename)
                            self._index_file(file_path)

        self._dirty = True
        self.save()
        log.info(f"Rebuilt index for {self.collection}: {len(self._index)} entries")

    def _index_file(self, file_path: str) -> None:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            doc_id = data.get('id')
            if doc_id:
                self._index[doc_id] = {
                    'path': file_path,
                    'created_at': data.get('created_at'),
                    'updated_at': data.get('updated_at')
                }
        except Exception as e:
            log.warning(f"Failed to index file {file_path}: {e}")

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            os.makedirs(self.collection_dir, exist_ok=True)
            try:
                with file_lock(self.index_path):
                    with open(self.index_path, 'w') as f:
                        json.dump(self._index, f, indent=2)
                self._dirty = False
            except Exception as e:
                log.error(f"Failed to save index for {self.collection}: {e}")

    def get(self, doc_id: str) -> Optional[str]:
        with self._lock:
            entry = self._index.get(doc_id)
            return entry['path'] if entry else None

    def set(self, doc_id: str, path: str, created_at: str = None, updated_at: str = None) -> None:
        with self._lock:
            self._index[doc_id] = {
                'path': path,
                'created_at': created_at or datetime.utcnow().isoformat(),
                'updated_at': updated_at or datetime.utcnow().isoformat()
            }
            self._dirty = True

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id in self._index:
                del self._index[doc_id]
                self._dirty = True
                return True
            return False

    def all_ids(self) -> list:
        with self._lock:
            return list(self._index.keys())

    def all_entries(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._index)

    def find_by_field(self, field: str, value: Any) -> list:
        with self._lock:
            return [doc_id for doc_id, entry in self._index.items() 
                    if entry.get(field) == value]

