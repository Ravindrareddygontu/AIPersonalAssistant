# MongoDB to File-Based Storage Migration Plan

## 1. Overview

### Goals
- Replace MongoDB with file-based JSON storage
- Maintain the same API/interface so routes don't require major changes
- Use folder structure: `data/{collection}/{year}/{month}/{day}/{id}.json`
- Handle concurrent access with file locking
- Zero downtime migration with backward compatibility

### Success Criteria
- All existing tests pass with mocked file operations
- Routes continue to work with same API contracts
- Data is persisted and queryable
- Concurrent access is handled safely
- No MongoDB dependency in production

### Scope
- **Included**: chats, bot_chats, reminders collections
- **Excluded**: AI middleware (uses Redis), session management (in-memory)

---

## 2. Prerequisites

### Dependencies to Add
```bash
pip install filelock aiofiles
```

### Configuration Changes
```python
# backend/config.py - New settings
FILE_STORAGE_BASE_DIR = os.environ.get('FILE_STORAGE_DIR', 
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'))
FILE_STORAGE_ENABLED = os.environ.get('FILE_STORAGE_ENABLED', 'true').lower() == 'true'
```

---

## 3. Implementation Steps

### Step 1: Create File Storage Module (`backend/storage/`)

**New file: `backend/storage/__init__.py`**
```python
from .file_storage import FileStorage
from .collections import ChatsCollection, RemindersCollection, BotChatsCollection
```

**New file: `backend/storage/file_storage.py`**
Core storage engine with:
- `_get_file_path(collection, id, created_at)` - Generate path: `data/{collection}/{year}/{month}/{day}/{id}.json`
- `_ensure_dir(path)` - Create directories if needed
- `_read_json(path)` - Read with file locking
- `_write_json(path, data)` - Write with file locking
- `_delete_file(path)` - Delete with locking
- Index management for fast lookups (in-memory + periodic persistence)

**Key design decisions:**
- Use `filelock` library for cross-process file locking
- Maintain in-memory index: `{collection: {id: {path, metadata}}}`
- Index persisted to `data/{collection}/_index.json`
- Index rebuilt on startup by scanning directories

### Step 2: Create Collection Classes (`backend/storage/collections.py`)

**ChatsCollection** - Implements same interface as MongoDB collection:
```python
class ChatsCollection:
    def find_one(self, filter: dict) -> dict | None
    def find(self, filter: dict = None, sort: list = None, limit: int = None) -> list
    def insert_one(self, document: dict) -> InsertResult
    def update_one(self, filter: dict, update: dict, upsert: bool = False) -> UpdateResult
    def delete_one(self, filter: dict) -> DeleteResult
    def delete_many(self, filter: dict = None) -> DeleteResult
```

**RemindersCollection** - Same interface

**BotChatsCollection** - Same interface plus:
```python
    def find_one_and_update(self, filter, update, upsert, return_document) -> dict
    def create_index(self, field, unique, background) -> None  # No-op for file storage
```

### Step 3: Update `backend/database.py`

Replace MongoDB functions with file storage:
```python
from backend.storage import FileStorage, ChatsCollection, RemindersCollection, BotChatsCollection

_storage = None
_chats = None
_reminders = None
_bot_chats = None

def get_storage():
    global _storage
    if _storage is None:
        _storage = FileStorage(FILE_STORAGE_BASE_DIR)
    return _storage

def is_connected() -> bool:
    return get_storage() is not None

def is_db_available_cached() -> bool:
    return True  # File storage always available

def check_connection() -> dict:
    return {'connected': True, 'storage': 'file'}

def get_chats_collection():
    global _chats
    if _chats is None:
        _chats = ChatsCollection(get_storage())
    return _chats

def get_reminders_collection():
    global _reminders
    if _reminders is None:
        _reminders = RemindersCollection(get_storage())
    return _reminders

def get_bot_chats_collection():
    global _bot_chats
    if _bot_chats is None:
        _bot_chats = BotChatsCollection(get_storage())
    return _bot_chats
```

### Step 4: Update Repository Classes

**`backend/services/chat_repository.py`** - Minimal changes:
- Remove `is_db_available_cached()` import (or keep, returns True)
- Collection interface unchanged, so code works as-is

**`backend/services/notification_service.py`** - Minimal changes:
- Same approach, collection interface unchanged

**`backend/services/bots/base_repository.py`** - Changes needed:
- `create_index()` calls become no-ops
- `find_one_and_update()` implemented in BotChatsCollection

**`backend/services/base_repository.py`** - Minimal changes:
- `is_db_available_cached()` now returns True always

### Step 5: Update Routes

**`backend/routes/settings.py`** - Changes:
- Remove MongoDB-specific error handling
- Update `/api/db/status` endpoint to return file storage status
- Chat CRUD operations work unchanged (collection interface)

**`backend/routes/chat.py`** - Minimal changes:
- `get_chats_collection()` still works, returns file-based collection



---

## 4. File Changes Summary

### Files to Create

| File | Purpose |
|------|---------|
| `backend/storage/__init__.py` | Module exports |
| `backend/storage/file_storage.py` | Core file storage engine (~150 lines) |
| `backend/storage/collections.py` | Collection classes with MongoDB-compatible interface (~250 lines) |
| `backend/storage/index.py` | Index management for fast lookups (~100 lines) |
| `backend/storage/locking.py` | File locking utilities (~50 lines) |
| `scripts/migrate_mongodb_to_files.py` | Migration script for existing data |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/config.py` | Add `FILE_STORAGE_BASE_DIR`, `FILE_STORAGE_ENABLED` |
| `backend/database.py` | Replace MongoDB with file storage imports and functions |
| `backend/services/base_repository.py` | Update `is_db_available_cached` behavior |
| `backend/services/bots/base_repository.py` | Handle `create_index` as no-op |
| `backend/routes/settings.py` | Update `/api/db/status` response |
| `requirements.txt` | Add `filelock`, `aiofiles` |
| `docker-compose.yml` | Remove MongoDB service, add data volume |
| `Dockerfile` | Remove MongoDB dependencies |
| `.env.example` | Add file storage config, remove MongoDB config |

### Files Unchanged (Interface Compatibility)

- `backend/services/chat_repository.py` - Uses collection interface
- `backend/services/notification_service.py` - Uses collection interface  
- `backend/routes/chat.py` - Uses `get_chats_collection()`
- `backend/routes/notifications.py` - Uses notification_service

---

## 5. Detailed File Storage Design

### Directory Structure
```
data/
├── chats/
│   ├── _index.json           # Index for fast lookups
│   └── 2026/
│       └── 02/
│           └── 21/
│               ├── abc12345.json
│               └── def67890.json
├── bot_chats/
│   ├── _index.json
│   └── 2026/02/21/...
└── reminders/
    ├── _index.json
    └── 2026/02/21/...
```

### Index File Format (`_index.json`)
```json
{
  "version": 1,
  "updated_at": "2026-02-21T10:30:00Z",
  "items": {
    "abc12345": {
      "path": "2026/02/21/abc12345.json",
      "created_at": "2026-02-21T09:00:00Z",
      "updated_at": "2026-02-21T10:30:00Z",
      "lookup_key": "slack:U123:C456"  // For bot_chats only
    }
  }
}
```

### Chat Document Format (unchanged from MongoDB)
```json
{
  "id": "abc12345",
  "title": "Chat Title",
  "created_at": "2026-02-21T09:00:00Z",
  "updated_at": "2026-02-21T10:30:00Z",
  "messages": [...],
  "workspace": "/path/to/workspace",
  "streaming_status": null,
  "provider": "auggie"
}
```

### File Locking Strategy
```python
from filelock import FileLock

def read_with_lock(path: str) -> dict:
    lock = FileLock(f"{path}.lock", timeout=5)
    with lock:
        with open(path, 'r') as f:
            return json.load(f)

def write_with_lock(path: str, data: dict) -> None:
    lock = FileLock(f"{path}.lock", timeout=5)
    with lock:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
```

---

## 6. Handling Concurrent Access

### Read Operations
- Use shared file locks for reads
- Index cached in memory, refreshed on writes

### Write Operations
- Use exclusive file locks
- Atomic writes: write to temp file, then rename
- Index updated after successful write

### Index Consistency
- In-memory index is primary (fast)
- Persisted index loaded on startup
- Index lock separate from file locks

### Race Conditions
- `find_one_and_update`: Lock file during entire operation
- `upsert`: Check existence under lock, then write

---

## 7. Testing Strategy

### Unit Tests to Update

| Test File | Changes |
|-----------|---------|
| `tests/test_chat_repository.py` | Mock `FileStorage` instead of MongoDB |
| `tests/test_notification_service.py` | Mock file collections |
| `tests/test_bot_chat_repository.py` | Mock `BotChatsCollection` |
| `tests/test_telegram_chat_repository.py` | Same approach |

### New Tests to Create

| Test File | Purpose |
|-----------|---------|
| `tests/test_file_storage.py` | Test core storage operations |
| `tests/test_collections.py` | Test collection interface compliance |
| `tests/test_file_locking.py` | Test concurrent access |
| `tests/test_migration.py` | Test migration script |

### Integration Tests
- Test chat CRUD with real file storage
- Test concurrent writes don't corrupt data
- Test index rebuilding on startup

---

## 8. Migration Strategy

### Phase 1: Preparation
1. Create backup of MongoDB data
2. Deploy file storage module alongside MongoDB
3. Run dual-write mode (write to both)

### Phase 2: Migration Script
```python
# scripts/migrate_mongodb_to_files.py
def migrate():
    # Connect to MongoDB
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client[MONGODB_DB_NAME]
    
    # Initialize file storage
    storage = FileStorage(FILE_STORAGE_BASE_DIR)
    
    # Migrate each collection
    for collection_name in ['chats', 'bot_chats', 'reminders']:
        mongo_col = db[collection_name]
        file_col = storage.get_collection(collection_name)
        
        for doc in mongo_col.find():
            doc.pop('_id', None)
            file_col.insert_one(doc)
        
        print(f"Migrated {mongo_col.count_documents({})} {collection_name}")
```

### Phase 3: Switchover
1. Run migration script
2. Update environment: `FILE_STORAGE_ENABLED=true`
3. Restart application
4. Verify data integrity
5. Remove MongoDB configuration

### Rollback Plan
1. Set `FILE_STORAGE_ENABLED=false`
2. Restart application (reverts to MongoDB)
3. MongoDB data preserved during migration

---

## 9. Docker/Deployment Changes

### docker-compose.yml (Updated)
```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: aipersonalassistant-app
    ports:
      - "5001:5001"
    environment:
      FLASK_ENV: production
      PYTHONUTF8: "1"
      FILE_STORAGE_DIR: /app/data
      DEFAULT_AI_PROVIDER: auggie
      DEFAULT_WORKSPACE: /root/projects
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      SLACK_ENABLED: "false"
    volumes:
      - app_data:/app/data          # Persistent file storage
      - ${USERPROFILE}/.augment:/root/.augment
      - ${USERPROFILE}/Desktop/projects:/root/projects
      - ./backend:/app/backend
      - ./static:/app/static
      - ./templates:/app/templates
    restart: unless-stopped

  # MongoDB service REMOVED

volumes:
  app_data:  # New volume for file storage
```

### Dockerfile Changes
```dockerfile
# Remove: RUN apt-get install ... mongodb-clients (if any)
# No MongoDB-related packages needed
```

### .gitignore Update
```
data/
*.lock
```

---

## 10. Estimated Effort

| Task | Complexity | Estimate |
|------|------------|----------|
| File storage module | Medium | 4-6 hours |
| Collection classes | Medium | 3-4 hours |
| Database.py refactor | Low | 1 hour |
| Repository updates | Low | 1-2 hours |
| Route updates | Low | 1 hour |
| Test updates | Medium | 3-4 hours |
| Migration script | Low | 1-2 hours |
| Docker changes | Low | 1 hour |
| Integration testing | Medium | 2-3 hours |
| **Total** | | **17-24 hours** |

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| File corruption | High | Atomic writes, backups |
| Concurrent access issues | Medium | File locking with `filelock` |
| Index out of sync | Medium | Rebuild index on startup |
| Large data sets slow | Medium | Index for fast lookups |
| Migration data loss | High | Run migration in parallel, keep MongoDB |

---

## 12. Implementation Order

1. **Day 1**: Create `backend/storage/` module with core classes
2. **Day 2**: Update `database.py` and test locally
3. **Day 3**: Update tests to mock file storage
4. **Day 4**: Create migration script, test with real data
5. **Day 5**: Update Docker configuration, deploy to staging
6. **Day 6**: Integration testing, bug fixes
7. **Day 7**: Production deployment with rollback capability
