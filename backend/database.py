

import logging
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from backend.config import MONGODB_URI, MONGODB_DB_NAME

log = logging.getLogger('database')

# MongoDB client singleton
_client = None
_db = None
_connection_error = None  # Track last connection error

# Caching for connection status to avoid repeated timeout waits
_last_connection_attempt = 0  # Timestamp of last connection attempt
_connection_available = None  # True/False/None (None = not checked yet)
_CACHE_DURATION_SUCCESS = 60  # Cache successful connection status for 60 seconds
_CACHE_DURATION_FAILURE = 5  # Cache failed connection status for 5 seconds (quick retry)
_CONNECTION_TIMEOUT_MS = 500  # Fast timeout (500ms) for quick failure detection


def is_connected() -> bool:
    global _client, _db
    if _client is None or _db is None:
        return False
    try:
        _client.admin.command('ping')
        return True
    except Exception:
        return False


def is_db_available_cached() -> bool:
    global _last_connection_attempt, _connection_available

    now = time.time()
    cache_duration = _CACHE_DURATION_SUCCESS if _connection_available else _CACHE_DURATION_FAILURE

    if _connection_available is not None and (now - _last_connection_attempt) < cache_duration:
        return _connection_available

    # Cache expired or not set, do actual check
    db = get_db()
    return db is not None


def check_connection() -> dict:
    global _connection_error, _connection_available

    # Use cached check to avoid timeout delays
    available = is_db_available_cached()

    if available:
        return {'connected': True}

    return {
        'connected': False,
        'error': str(_connection_error) if _connection_error else 'MongoDB not available'
    }


def get_db():
    global _client, _db, _connection_error, _last_connection_attempt, _connection_available

    now = time.time()

    # If we recently failed to connect, return None immediately (cached failure)
    if _connection_available is False and (now - _last_connection_attempt) < _CACHE_DURATION_FAILURE:
        return None

    if _db is not None:
        # Verify connection is still alive
        try:
            _client.admin.command('ping')
            return _db
        except Exception:
            # Connection lost, reset and try again
            _client = None
            _db = None
            _connection_available = None

    try:
        _last_connection_attempt = now
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=_CONNECTION_TIMEOUT_MS)
        # Test connection
        _client.admin.command('ping')
        _db = _client[MONGODB_DB_NAME]
        _connection_error = None
        _connection_available = True
        log.info(f"Connected to MongoDB: {MONGODB_URI}, database: {MONGODB_DB_NAME}")
        return _db
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        _connection_error = e
        _connection_available = False
        log.warning(f"MongoDB not available: {e}. Running in degraded mode (no persistence).")
        return None
    except Exception as e:
        _connection_error = e
        _connection_available = False
        log.warning(f"MongoDB connection error: {e}. Running in degraded mode.")
        return None


def get_chats_collection():
    db = get_db()
    if db is None:
        return None
    return db['chats']


def get_reminders_collection():
    db = get_db()
    if db is None:
        return None
    return db['reminders']
