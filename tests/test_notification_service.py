"""
Tests for notification_service.py - Reminder CRUD operations.

Tests cover:
- create_reminder: Creating new reminders
- get_all_reminders: Retrieving all reminders
- get_reminder: Retrieving single reminder
- update_reminder: Updating reminder fields
- delete_reminder: Deleting reminders
- toggle_reminder: Toggling enabled state
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCreateReminder:
    """Test reminder creation."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_create_reminder_basic(self, mock_collection):
        """Test basic reminder creation."""
        from backend.services.notification_service import create_reminder
        
        mock_col = MagicMock()
        mock_collection.return_value = mock_col
        
        result = create_reminder(
            title="Test Reminder",
            message="Test message",
            time="09:00",
            days=['mon', 'tue', 'wed']
        )
        
        assert result['title'] == "Test Reminder"
        assert result['message'] == "Test message"
        assert result['time'] == "09:00"
        assert result['days'] == ['mon', 'tue', 'wed']
        assert result['enabled'] == True
        assert 'id' in result
        assert 'created_at' in result
        assert '_id' not in result
        
        mock_col.insert_one.assert_called_once()

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_create_reminder_id_format(self, mock_collection):
        """Test that reminder ID is 8 characters."""
        from backend.services.notification_service import create_reminder
        
        mock_collection.return_value = MagicMock()
        
        result = create_reminder("Test", "Msg", "10:00", ['fri'])
        assert len(result['id']) == 8


class TestGetAllReminders:
    """Test retrieving all reminders."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_get_all_reminders_empty(self, mock_collection):
        """Test getting reminders when none exist."""
        from backend.services.notification_service import get_all_reminders
        
        mock_col = MagicMock()
        mock_col.find.return_value = []
        mock_collection.return_value = mock_col
        
        result = get_all_reminders()
        assert result == []

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_get_all_reminders_multiple(self, mock_collection):
        """Test getting multiple reminders."""
        from backend.services.notification_service import get_all_reminders
        
        mock_col = MagicMock()
        mock_col.find.return_value = [
            {'_id': 'obj1', 'id': 'rem1', 'title': 'R1'},
            {'_id': 'obj2', 'id': 'rem2', 'title': 'R2'},
        ]
        mock_collection.return_value = mock_col
        
        result = get_all_reminders()
        
        assert len(result) == 2
        assert all('_id' not in r for r in result)
        assert result[0]['title'] == 'R1'
        assert result[1]['title'] == 'R2'


class TestGetReminder:
    """Test retrieving single reminder."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_get_reminder_found(self, mock_collection):
        """Test getting existing reminder."""
        from backend.services.notification_service import get_reminder
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = {'_id': 'obj1', 'id': 'rem1', 'title': 'Test'}
        mock_collection.return_value = mock_col
        
        result = get_reminder('rem1')
        
        assert result is not None
        assert result['title'] == 'Test'
        assert '_id' not in result
        mock_col.find_one.assert_called_with({'id': 'rem1'})

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_get_reminder_not_found(self, mock_collection):
        """Test getting non-existent reminder."""
        from backend.services.notification_service import get_reminder
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection.return_value = mock_col
        
        result = get_reminder('nonexistent')
        assert result is None


class TestUpdateReminder:
    """Test updating reminders."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_update_reminder_success(self, mock_collection):
        """Test successful reminder update."""
        from backend.services.notification_service import update_reminder
        
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(modified_count=1)
        mock_col.find_one.return_value = {'id': 'rem1', 'title': 'Updated'}
        mock_collection.return_value = mock_col
        
        result = update_reminder('rem1', {'title': 'Updated'})
        
        assert result is not None
        assert result['title'] == 'Updated'

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_update_reminder_not_found(self, mock_collection):
        """Test updating non-existent reminder."""
        from backend.services.notification_service import update_reminder
        
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(modified_count=0)
        mock_collection.return_value = mock_col
        
        result = update_reminder('nonexistent', {'title': 'New'})
        assert result is None

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_update_ignores_protected_fields(self, mock_collection):
        """Test that id, _id, created_at cannot be updated."""
        from backend.services.notification_service import update_reminder
        
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(modified_count=1)
        mock_col.find_one.return_value = {'id': 'rem1'}
        mock_collection.return_value = mock_col
        
        update_reminder('rem1', {
            'id': 'new-id',
            '_id': 'new-obj-id',
            'created_at': '2020-01-01',
            'title': 'Valid Update'
        })
        
        # Check that protected fields were removed
        call_args = mock_col.update_one.call_args
        update_dict = call_args[0][1]['$set']
        assert 'id' not in update_dict
        assert '_id' not in update_dict
        assert 'created_at' not in update_dict
        assert update_dict['title'] == 'Valid Update'


class TestDeleteReminder:
    """Test deleting reminders."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_delete_reminder_success(self, mock_collection):
        """Test successful reminder deletion."""
        from backend.services.notification_service import delete_reminder
        
        mock_col = MagicMock()
        mock_col.delete_one.return_value = MagicMock(deleted_count=1)
        mock_collection.return_value = mock_col
        
        result = delete_reminder('rem1')
        
        assert result == True
        mock_col.delete_one.assert_called_with({'id': 'rem1'})

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_delete_reminder_not_found(self, mock_collection):
        """Test deleting non-existent reminder."""
        from backend.services.notification_service import delete_reminder
        
        mock_col = MagicMock()
        mock_col.delete_one.return_value = MagicMock(deleted_count=0)
        mock_collection.return_value = mock_col
        
        result = delete_reminder('nonexistent')
        assert result == False


class TestToggleReminder:
    """Test toggling reminder enabled state."""

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_toggle_reminder_enable(self, mock_collection):
        """Test toggling from disabled to enabled."""
        from backend.services.notification_service import toggle_reminder
        
        mock_col = MagicMock()
        mock_col.find_one.side_effect = [
            {'id': 'rem1', 'enabled': False},  # First call - get_reminder
            {'id': 'rem1', 'enabled': True},   # Second call - after update
        ]
        mock_col.update_one.return_value = MagicMock(modified_count=1)
        mock_collection.return_value = mock_col
        
        result = toggle_reminder('rem1')
        
        assert result is not None
        # Verify update was called with enabled=True
        call_args = mock_col.update_one.call_args
        assert call_args[0][1]['$set']['enabled'] == True

    @patch('backend.services.notification_service.get_reminders_collection')
    def test_toggle_reminder_not_found(self, mock_collection):
        """Test toggling non-existent reminder."""
        from backend.services.notification_service import toggle_reminder
        
        mock_col = MagicMock()
        mock_col.find_one.return_value = None
        mock_collection.return_value = mock_col
        
        result = toggle_reminder('nonexistent')
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

