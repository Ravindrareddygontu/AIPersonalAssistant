#!/usr/bin/env python3
"""
Migration script: MongoDB to File-based Storage

Migrates data from MongoDB collections to file-based JSON storage.
Structure: data/{collection}/{year}/{month}/{day}/{id}.json

Usage:
    python scripts/migrate_mongodb_to_files.py [--dry-run] [--collection COLLECTION]

Options:
    --dry-run       Show what would be migrated without making changes
    --collection    Migrate only a specific collection (chats, bot_chats, reminders)
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import FILE_STORAGE_BASE_DIR, MONGODB_URI, MONGODB_DB_NAME
from backend.storage import FileStorage, ChatsCollection, RemindersCollection, BotChatsCollection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('migrate')

COLLECTIONS = {
    'chats': ChatsCollection,
    'bot_chats': BotChatsCollection,
    'reminders': RemindersCollection,
}


def get_mongodb_connection():
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        log.info(f"Connected to MongoDB: {MONGODB_URI}")
        return client, client[MONGODB_DB_NAME]
    except Exception as e:
        log.error(f"Failed to connect to MongoDB: {e}")
        return None, None


def migrate_collection(mongo_db, file_storage, collection_name, dry_run=False):
    log.info(f"Migrating collection: {collection_name}")
    
    mongo_col = mongo_db[collection_name]
    file_col_class = COLLECTIONS.get(collection_name)
    
    if not file_col_class:
        log.error(f"Unknown collection: {collection_name}")
        return 0, 0
    
    file_col = file_col_class(file_storage)
    
    total = mongo_col.count_documents({})
    migrated = 0
    errors = 0
    
    log.info(f"Found {total} documents in {collection_name}")
    
    for doc in mongo_col.find():
        try:
            doc_id = doc.get('id') or str(doc.get('_id'))
            doc.pop('_id', None)
            
            if not doc.get('id'):
                doc['id'] = doc_id
            
            if dry_run:
                log.info(f"  [DRY-RUN] Would migrate: {doc_id}")
            else:
                file_col.insert_one(doc)
                log.debug(f"  Migrated: {doc_id}")
            
            migrated += 1
            
            if migrated % 100 == 0:
                log.info(f"  Progress: {migrated}/{total}")
                
        except Exception as e:
            log.error(f"  Failed to migrate document: {e}")
            errors += 1
    
    log.info(f"Completed {collection_name}: {migrated} migrated, {errors} errors")
    return migrated, errors


def main():
    parser = argparse.ArgumentParser(description='Migrate MongoDB to file storage')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--collection', choices=list(COLLECTIONS.keys()), help='Specific collection')
    args = parser.parse_args()
    
    client, mongo_db = get_mongodb_connection()
    if not mongo_db:
        log.error("Cannot proceed without MongoDB connection")
        sys.exit(1)
    
    file_storage = FileStorage(FILE_STORAGE_BASE_DIR)
    log.info(f"File storage initialized at: {FILE_STORAGE_BASE_DIR}")
    
    collections_to_migrate = [args.collection] if args.collection else list(COLLECTIONS.keys())
    
    total_migrated = 0
    total_errors = 0
    
    for col_name in collections_to_migrate:
        migrated, errors = migrate_collection(mongo_db, file_storage, col_name, args.dry_run)
        total_migrated += migrated
        total_errors += errors
    
    log.info("=" * 50)
    log.info(f"Migration {'simulation ' if args.dry_run else ''}complete!")
    log.info(f"Total: {total_migrated} documents migrated, {total_errors} errors")
    
    if args.dry_run:
        log.info("Run without --dry-run to perform actual migration")
    
    client.close()


if __name__ == '__main__':
    main()

