"""
Notification Routes - API endpoints for managing reminders.
Reminders are stored in MongoDB and scheduled client-side using setTimeout.
"""

import json
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services import notification_service as notif_svc

log = logging.getLogger('notifications')
notifications_router = APIRouter()


# Pydantic models
class ReminderCreate(BaseModel):
    title: str = 'Reminder'
    message: str = ''
    time: str = '09:00'
    days: List[str] = ['mon', 'tue', 'wed', 'thu', 'fri']


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    time: Optional[str] = None
    days: Optional[List[str]] = None
    enabled: Optional[bool] = None


def _log_request(method: str, url: str, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


def _log_response(method: str, url: str, status: int, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[RESPONSE] {method} {url} | Status: {status} | Body: {body_str}")


@notifications_router.get('/api/reminders')
async def list_reminders(request: Request):
    """Get all reminders."""
    url = str(request.url)
    _log_request('GET', url)

    reminders = notif_svc.get_all_reminders()
    _log_response('GET', url, 200, {'count': len(reminders)})
    return reminders


@notifications_router.post('/api/reminders', status_code=201)
async def create_reminder(request: Request, data: ReminderCreate):
    """Create a new reminder."""
    url = str(request.url)
    _log_request('POST', url, data.model_dump())

    reminder = notif_svc.create_reminder(data.title, data.message, data.time, data.days)
    _log_response('POST', url, 201, reminder)
    return reminder


@notifications_router.get('/api/reminders/{reminder_id}')
async def get_reminder(request: Request, reminder_id: str):
    """Get a specific reminder."""
    url = str(request.url)
    _log_request('GET', url)

    reminder = notif_svc.get_reminder(reminder_id)
    if reminder:
        _log_response('GET', url, 200, reminder)
        return reminder

    _log_response('GET', url, 404, {'error': 'Not found'})
    return JSONResponse(content={'error': 'Reminder not found'}, status_code=404)


@notifications_router.put('/api/reminders/{reminder_id}')
async def update_reminder(request: Request, reminder_id: str, data: ReminderUpdate):
    """Update a reminder."""
    url = str(request.url)
    data_dict = data.model_dump(exclude_none=True)
    _log_request('PUT', url, data_dict)

    reminder = notif_svc.update_reminder(reminder_id, data_dict)
    if reminder:
        _log_response('PUT', url, 200, reminder)
        return reminder

    _log_response('PUT', url, 404, {'error': 'Not found'})
    return JSONResponse(content={'error': 'Reminder not found'}, status_code=404)


@notifications_router.delete('/api/reminders/{reminder_id}')
async def delete_reminder(request: Request, reminder_id: str):
    """Delete a reminder."""
    url = str(request.url)
    _log_request('DELETE', url)

    if notif_svc.delete_reminder(reminder_id):
        _log_response('DELETE', url, 200, {'status': 'deleted'})
        return {'status': 'deleted'}

    _log_response('DELETE', url, 404, {'error': 'Not found'})
    return JSONResponse(content={'error': 'Reminder not found'}, status_code=404)


@notifications_router.post('/api/reminders/{reminder_id}/toggle')
async def toggle_reminder(request: Request, reminder_id: str):
    """Toggle a reminder's enabled state."""
    url = str(request.url)
    _log_request('POST', url)

    reminder = notif_svc.toggle_reminder(reminder_id)
    if reminder:
        _log_response('POST', url, 200, reminder)
        return reminder

    _log_response('POST', url, 404, {'error': 'Not found'})
    return JSONResponse(content={'error': 'Reminder not found'}, status_code=404)


