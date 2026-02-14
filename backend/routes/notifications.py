"""
Notification Routes - API endpoints for managing reminders.
Reminders are stored in MongoDB and scheduled client-side using setTimeout.
"""

import json
import logging
from flask import Blueprint, request, jsonify

from backend.services import notification_service as notif_svc

log = logging.getLogger('notifications')
notifications_bp = Blueprint('notifications', __name__)


def _log_request(method, url, body=None):
    body_str = json.dumps(body)[:500] if body else 'None'
    log.info(f"[REQUEST] {method} {url} | Body: {body_str}")


@notifications_bp.route('/api/reminders', methods=['GET'])
def list_reminders():
    """Get all reminders."""
    url = request.url
    _log_request('GET', url)
    
    reminders = notif_svc.get_all_reminders()
    _log_response('GET', url, 200, {'count': len(reminders)})
    return jsonify(reminders)


@notifications_bp.route('/api/reminders', methods=['POST'])
def create_reminder():
    """Create a new reminder."""
    url = request.url
    data = request.json
    _log_request('POST', url, data)
    
    title = data.get('title', 'Reminder')
    message = data.get('message', '')
    time = data.get('time', '09:00')
    days = data.get('days', ['mon', 'tue', 'wed', 'thu', 'fri'])
    
    reminder = notif_svc.create_reminder(title, message, time, days)
    _log_response('POST', url, 201, reminder)
    return jsonify(reminder), 201


@notifications_bp.route('/api/reminders/<reminder_id>', methods=['GET'])
def get_reminder(reminder_id):
    """Get a specific reminder."""
    url = request.url
    _log_request('GET', url)
    
    reminder = notif_svc.get_reminder(reminder_id)
    if reminder:
        _log_response('GET', url, 200, reminder)
        return jsonify(reminder)
    
    _log_response('GET', url, 404, {'error': 'Not found'})
    return jsonify({'error': 'Reminder not found'}), 404


@notifications_bp.route('/api/reminders/<reminder_id>', methods=['PUT'])
def update_reminder(reminder_id):
    """Update a reminder."""
    url = request.url
    data = request.json
    _log_request('PUT', url, data)
    
    reminder = notif_svc.update_reminder(reminder_id, data)
    if reminder:
        _log_response('PUT', url, 200, reminder)
        return jsonify(reminder)
    
    _log_response('PUT', url, 404, {'error': 'Not found'})
    return jsonify({'error': 'Reminder not found'}), 404


@notifications_bp.route('/api/reminders/<reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id):
    """Delete a reminder."""
    url = request.url
    _log_request('DELETE', url)
    
    if notif_svc.delete_reminder(reminder_id):
        _log_response('DELETE', url, 200, {'status': 'deleted'})
        return jsonify({'status': 'deleted'})
    
    _log_response('DELETE', url, 404, {'error': 'Not found'})
    return jsonify({'error': 'Reminder not found'}), 404


@notifications_bp.route('/api/reminders/<reminder_id>/toggle', methods=['POST'])
def toggle_reminder(reminder_id):
    """Toggle a reminder's enabled state."""
    url = request.url
    _log_request('POST', url)
    
    reminder = notif_svc.toggle_reminder(reminder_id)
    if reminder:
        _log_response('POST', url, 200, reminder)
        return jsonify(reminder)
    
    _log_response('POST', url, 404, {'error': 'Not found'})
    return jsonify({'error': 'Reminder not found'}), 404


