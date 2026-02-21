import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Any, Dict

from .file_storage import FileStorage

log = logging.getLogger('storage.collections')


@dataclass
class InsertResult:
    inserted_id: str
    acknowledged: bool = True


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int
    upserted_id: Optional[str] = None
    acknowledged: bool = True


@dataclass
class DeleteResult:
    deleted_count: int
    acknowledged: bool = True


class BaseCollection:
    COLLECTION_NAME = 'base'

    def __init__(self, storage: FileStorage):
        self.storage = storage
        self.collection_name = self.COLLECTION_NAME

    def _match_filter(self, doc: dict, filter: dict) -> bool:
        if not filter:
            return True
        for key, value in filter.items():
            if key.startswith('$'):
                continue
            doc_value = doc.get(key)
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == '$gt' and not (doc_value and doc_value > op_value):
                        return False
                    elif op == '$gte' and not (doc_value and doc_value >= op_value):
                        return False
                    elif op == '$lt' and not (doc_value and doc_value < op_value):
                        return False
                    elif op == '$lte' and not (doc_value and doc_value <= op_value):
                        return False
                    elif op == '$ne' and doc_value == op_value:
                        return False
                    elif op == '$in' and doc_value not in op_value:
                        return False
            elif doc_value != value:
                return False
        return True

    def _apply_update(self, doc: dict, update: dict) -> dict:
        for op, fields in update.items():
            if op == '$set':
                for key, value in fields.items():
                    doc[key] = value
            elif op == '$unset':
                for key in fields:
                    doc.pop(key, None)
            elif op == '$push':
                for key, value in fields.items():
                    if key not in doc:
                        doc[key] = []
                    doc[key].append(value)
            elif op == '$pull':
                for key, value in fields.items():
                    if key in doc and isinstance(doc[key], list):
                        doc[key] = [x for x in doc[key] if x != value]
            elif op == '$inc':
                for key, value in fields.items():
                    doc[key] = doc.get(key, 0) + value
        return doc

    def find_one(self, filter: dict = None) -> Optional[dict]:
        if filter and 'id' in filter:
            doc = self.storage.read(self.collection_name, filter['id'])
            if doc and self._match_filter(doc, filter):
                return doc
            return None

        for doc in self.storage.list_all(self.collection_name):
            if self._match_filter(doc, filter):
                return doc
        return None

    def find(self, filter: dict = None, sort: list = None, limit: int = None) -> list:
        results = []
        for doc in self.storage.list_all(self.collection_name):
            if self._match_filter(doc, filter):
                results.append(doc)

        if sort:
            for sort_field, direction in reversed(sort):
                reverse = direction == -1
                results.sort(key=lambda x: x.get(sort_field, ''), reverse=reverse)

        if limit:
            results = results[:limit]

        return results

    def insert_one(self, document: dict) -> InsertResult:
        if 'id' not in document:
            document['id'] = str(uuid.uuid4())[:8]
        if 'created_at' not in document:
            document['created_at'] = datetime.utcnow().isoformat()
        if 'updated_at' not in document:
            document['updated_at'] = document['created_at']

        self.storage.write(self.collection_name, document['id'], document)
        log.info(f"Inserted document {document['id']} into {self.collection_name}")
        return InsertResult(inserted_id=document['id'])

    def update_one(self, filter: dict, update: dict, upsert: bool = False) -> UpdateResult:
        doc = self.find_one(filter)

        if doc:
            updated_doc = self._apply_update(doc.copy(), update)
            updated_doc['updated_at'] = datetime.utcnow().isoformat()
            self.storage.write(self.collection_name, doc['id'], updated_doc)
            return UpdateResult(matched_count=1, modified_count=1)
        elif upsert:
            new_doc = filter.copy()
            new_doc = self._apply_update(new_doc, update)
            result = self.insert_one(new_doc)
            return UpdateResult(matched_count=0, modified_count=0, upserted_id=result.inserted_id)

        return UpdateResult(matched_count=0, modified_count=0)

    def delete_one(self, filter: dict) -> DeleteResult:
        doc = self.find_one(filter)
        if doc:
            self.storage.delete(self.collection_name, doc['id'])
            log.info(f"Deleted document {doc['id']} from {self.collection_name}")
            return DeleteResult(deleted_count=1)
        return DeleteResult(deleted_count=0)

    def delete_many(self, filter: dict = None) -> DeleteResult:
        docs = self.find(filter)
        count = 0
        for doc in docs:
            if self.storage.delete(self.collection_name, doc['id']):
                count += 1
        log.info(f"Deleted {count} documents from {self.collection_name}")
        return DeleteResult(deleted_count=count)

    def count_documents(self, filter: dict = None) -> int:
        return len(self.find(filter))


class ChatsCollection(BaseCollection):
    COLLECTION_NAME = 'chats'


class RemindersCollection(BaseCollection):
    COLLECTION_NAME = 'reminders'


class BotChatsCollection(BaseCollection):
    COLLECTION_NAME = 'bot_chats'

    def find_one_and_update(self, filter: dict, update: dict, upsert: bool = False,
                            return_document: str = 'after') -> Optional[dict]:
        doc = self.find_one(filter)

        if doc:
            updated_doc = self._apply_update(doc.copy(), update)
            updated_doc['updated_at'] = datetime.utcnow().isoformat()
            self.storage.write(self.collection_name, doc['id'], updated_doc)
            return updated_doc if return_document == 'after' else doc
        elif upsert:
            new_doc = {}
            for key, value in filter.items():
                if not key.startswith('$'):
                    new_doc[key] = value
            new_doc = self._apply_update(new_doc, update)
            if 'id' not in new_doc:
                new_doc['id'] = str(uuid.uuid4())[:8]
            new_doc['created_at'] = datetime.utcnow().isoformat()
            new_doc['updated_at'] = new_doc['created_at']
            self.storage.write(self.collection_name, new_doc['id'], new_doc)
            return new_doc if return_document == 'after' else None

        return None

    def create_index(self, field: str, unique: bool = False, background: bool = True) -> None:
        log.debug(f"create_index called for {field} (no-op for file storage)")

