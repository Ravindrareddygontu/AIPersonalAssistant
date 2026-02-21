import logging

from backend.config import FILE_STORAGE_BASE_DIR, FILE_STORAGE_ENABLED
from backend.storage import FileStorage, ChatsCollection, RemindersCollection, BotChatsCollection

log = logging.getLogger('database')

_storage = None
_chats = None
_reminders = None
_bot_chats = None


def get_storage() -> FileStorage:
    global _storage
    if _storage is None:
        _storage = FileStorage(FILE_STORAGE_BASE_DIR)
        log.info(f"Initialized file storage at {FILE_STORAGE_BASE_DIR}")
    return _storage


def is_connected() -> bool:
    return get_storage() is not None


def is_db_available_cached() -> bool:
    return FILE_STORAGE_ENABLED


def check_connection() -> dict:
    if is_db_available_cached():
        return {'connected': True, 'storage': 'file', 'path': FILE_STORAGE_BASE_DIR}
    return {'connected': False, 'error': 'File storage disabled'}


def get_chats_collection() -> ChatsCollection:
    global _chats
    if not FILE_STORAGE_ENABLED:
        return None
    if _chats is None:
        _chats = ChatsCollection(get_storage())
    return _chats


def get_reminders_collection() -> RemindersCollection:
    global _reminders
    if not FILE_STORAGE_ENABLED:
        return None
    if _reminders is None:
        _reminders = RemindersCollection(get_storage())
    return _reminders


def get_bot_chats_collection() -> BotChatsCollection:
    global _bot_chats
    if not FILE_STORAGE_ENABLED:
        return None
    if _bot_chats is None:
        _bot_chats = BotChatsCollection(get_storage())
    return _bot_chats


# Legacy function for migration purposes
def get_mongodb_client():
    try:
        from pymongo import MongoClient
        from backend.config import MONGODB_URI, MONGODB_DB_NAME
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        return client, client[MONGODB_DB_NAME]
    except Exception as e:
        log.warning(f"MongoDB not available for migration: {e}")
        return None, None
