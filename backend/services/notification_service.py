"""
Notification Service - CRUD operations for reminders.
Scheduling is done client-side using setTimeout for efficiency.

Reminder Schema:
{
    id: 'unique-id',
    title: 'Punch In Reminder',
    message: 'Time to punch in!',
    time: '11:00',  # HH:MM format
    days: ['mon', 'tue', 'wed', 'thu', 'fri'],  # Days of week
    enabled: true,
    created_at: 'ISO timestamp'
}
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from backend.database import get_reminders_collection

log = logging.getLogger('notifications')


# CRUD Operations

def create_reminder(title: str, message: str, time: str, days: List[str]) -> dict:
    """Create a new reminder."""
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
    collection.insert_one(reminder)
    reminder.pop('_id', None)

    log.info(f"Created reminder: {title}")
    return reminder


def get_all_reminders() -> List[dict]:
    """Get all reminders."""
    collection = get_reminders_collection()
    reminders = list(collection.find())
    for r in reminders:
        r.pop('_id', None)
    return reminders


def get_reminder(reminder_id: str) -> Optional[dict]:
    """Get a reminder by ID."""
    collection = get_reminders_collection()
    reminder = collection.find_one({'id': reminder_id})
    if reminder:
        reminder.pop('_id', None)
    return reminder


def update_reminder(reminder_id: str, updates: dict) -> Optional[dict]:
    """Update a reminder."""
    collection = get_reminders_collection()

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
    """Delete a reminder."""
    collection = get_reminders_collection()
    result = collection.delete_one({'id': reminder_id})

    if result.deleted_count > 0:
        log.info(f"Deleted reminder {reminder_id}")
        return True
    return False


def toggle_reminder(reminder_id: str) -> Optional[dict]:
    """Toggle a reminder's enabled state."""
    reminder = get_reminder(reminder_id)
    if reminder:
        new_state = not reminder.get('enabled', True)
        return update_reminder(reminder_id, {'enabled': new_state})
    return None

