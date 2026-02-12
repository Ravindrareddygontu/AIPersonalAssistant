"""MongoDB database module for chat storage."""

import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from backend.config import MONGODB_URI, MONGODB_DB_NAME

log = logging.getLogger('database')

# MongoDB client singleton
_client = None
_db = None


def get_db():
    """Get MongoDB database instance."""
    global _client, _db
    if _db is None:
        try:
            _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Test connection
            _client.admin.command('ping')
            _db = _client[MONGODB_DB_NAME]
            log.info(f"Connected to MongoDB: {MONGODB_URI}, database: {MONGODB_DB_NAME}")
        except ConnectionFailure as e:
            log.error(f"Failed to connect to MongoDB: {e}")
            raise
    return _db


def get_chats_collection():
    """Get the chats collection."""
    return get_db()['chats']


def close_connection():
    """Close MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        log.info("MongoDB connection closed")

