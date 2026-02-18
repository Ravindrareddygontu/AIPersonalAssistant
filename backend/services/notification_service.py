import logging
import uuid
from datetime import datetime
from typing import List, Optional

from backend.database import get_reminders_collection, is_db_available_cached

log = logging.getLogger('notifications')


# CRUD Operations

def create_reminder(title: str, message: str, time: str, days: List[str]) -> Optional[dict]:
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        log.warning("MongoDB not available (cached), cannot create reminder")
        return None

    reminder = {
        'id': str(uuid.uuid4())[:8],
        'title': title,
        'message': message,
        'time': time,
        'days': days,
        'enabled': True,
        'created_at': datetime.utcnow().isoformat()
    }

    collection = get_reminders_collection()
    if collection is None:
        log.warning("MongoDB not available, cannot create reminder")
        return None

    collection.insert_one(reminder)
    reminder.pop('_id', None)

    log.info(f"Created reminder: {title}")
    return reminder


def get_all_reminders() -> List[dict]:
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        log.warning("MongoDB not available (cached), returning empty reminders list")
        return []

    collection = get_reminders_collection()
    if collection is None:
        log.warning("MongoDB not available, returning empty reminders list")
        return []

    reminders = list(collection.find())
    for r in reminders:
        r.pop('_id', None)
    return reminders


def get_reminder(reminder_id: str) -> Optional[dict]:
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        log.warning("MongoDB not available (cached), cannot get reminder")
        return None

    collection = get_reminders_collection()
    if collection is None:
        log.warning("MongoDB not available, cannot get reminder")
        return None

    reminder = collection.find_one({'id': reminder_id})
    if reminder:
        reminder.pop('_id', None)
    return reminder


def update_reminder(reminder_id: str, updates: dict) -> Optional[dict]:
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        log.warning("MongoDB not available (cached), cannot update reminder")
        return None

    collection = get_reminders_collection()
    if collection is None:
        log.warning("MongoDB not available, cannot update reminder")
        return None

    # Don't allow updating id or created_at
    updates.pop('id', None)
    updates.pop('_id', None)
    updates.pop('created_at', None)

    result = collection.update_one(
        {'id': reminder_id},
        {'$set': updates}
    )

    if result.modified_count > 0:
        return get_reminder(reminder_id)
    return None


def delete_reminder(reminder_id: str) -> bool:
    # Quick check using cached status first (non-blocking)
    if not is_db_available_cached():
        log.warning("MongoDB not available (cached), cannot delete reminder")
        return False

    collection = get_reminders_collection()
    if collection is None:
        log.warning("MongoDB not available, cannot delete reminder")
        return False

    result = collection.delete_one({'id': reminder_id})

    if result.deleted_count > 0:
        log.info(f"Deleted reminder {reminder_id}")
        return True
    return False


def toggle_reminder(reminder_id: str) -> Optional[dict]:
    reminder = get_reminder(reminder_id)
    if reminder:
        new_state = not reminder.get('enabled', True)
        return update_reminder(reminder_id, {'enabled': new_state})
    return None

