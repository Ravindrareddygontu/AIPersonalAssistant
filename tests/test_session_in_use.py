"""
Tests for session in_use flag functionality.

This tests that sessions with an active terminal (in_use=True) are not
deleted during cleanup or reset operations.
"""

import pytest
import sys
import os
import time
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.session import AuggieSession, SessionManager, _sessions, _lock


class TestAuggieSessionInUse:
    """Test AuggieSession in_use flag behavior."""

    def test_session_init_in_use_false(self):
        """Test that new sessions start with in_use=False."""
        session = AuggieSession('/tmp/test-workspace')
        assert session.in_use == False

    def test_session_in_use_can_be_set(self):
        """Test that in_use flag can be set and cleared."""
        session = AuggieSession('/tmp/test-workspace')
        
        session.in_use = True
        assert session.in_use == True
        
        session.in_use = False
        assert session.in_use == False


class TestSessionManagerCleanupOld:
    """Test SessionManager.cleanup_old() respects in_use flag."""

    def setup_method(self):
        """Clear sessions before each test."""
        with _lock:
            _sessions.clear()

    def teardown_method(self):
        """Clean up after each test."""
        with _lock:
            for session in _sessions.values():
                try:
                    session.cleanup()
                except:
                    pass
            _sessions.clear()

    def test_cleanup_old_skips_in_use_session(self):
        """Test that cleanup_old skips sessions with in_use=True."""
        workspace = '/tmp/test-cleanup-in-use'
        
        # Create a mock session that's old but in use
        session = AuggieSession(workspace)
        session.last_used = time.time() - 700  # Over 600 seconds old
        session.in_use = True
        session.process = MagicMock()
        session.process.poll.return_value = None  # Process is alive
        session.process.pid = 12345
        
        with _lock:
            _sessions[workspace] = session
        
        # Run cleanup
        with patch('backend.session.cleanup_stale_auggie_processes'):
            SessionManager.cleanup_old()
        
        # Session should still exist because it's in use
        with _lock:
            assert workspace in _sessions
            assert _sessions[workspace].in_use == True

    def test_cleanup_old_removes_old_session_not_in_use(self):
        """Test that cleanup_old removes old sessions that are not in use."""
        workspace = '/tmp/test-cleanup-not-in-use'
        
        # Create a mock session that's old and not in use
        session = AuggieSession(workspace)
        session.last_used = time.time() - 700  # Over 600 seconds old
        session.in_use = False
        session.process = None  # No process to clean up
        session.master_fd = None
        
        with _lock:
            _sessions[workspace] = session
        
        # Run cleanup
        with patch('backend.session.cleanup_stale_auggie_processes'):
            SessionManager.cleanup_old()
        
        # Session should be removed
        with _lock:
            assert workspace not in _sessions

    def test_cleanup_old_keeps_recent_sessions(self):
        """Test that cleanup_old keeps recent sessions regardless of in_use."""
        workspace = '/tmp/test-cleanup-recent'
        
        # Create a mock session that's recent
        session = AuggieSession(workspace)
        session.last_used = time.time() - 100  # Only 100 seconds old
        session.in_use = False
        
        with _lock:
            _sessions[workspace] = session
        
        # Run cleanup
        with patch('backend.session.cleanup_stale_auggie_processes'):
            SessionManager.cleanup_old()
        
        # Session should still exist
        with _lock:
            assert workspace in _sessions


class TestSessionManagerReset:
    """Test SessionManager.reset() respects in_use flag."""

    def setup_method(self):
        """Clear sessions before each test."""
        with _lock:
            _sessions.clear()

    def teardown_method(self):
        """Clean up after each test."""
        with _lock:
            for session in _sessions.values():
                try:
                    session.cleanup()
                except:
                    pass
            _sessions.clear()

    def test_reset_returns_false_when_in_use(self):
        """Test that reset returns False when session is in use."""
        workspace = '/tmp/test-reset-in-use'
        
        # Create a session that's in use
        session = AuggieSession(workspace)
        session.in_use = True
        session.process = MagicMock()
        session.process.poll.return_value = None
        session.process.pid = 12345
        
        with _lock:
            _sessions[workspace] = session
        
        # Try to reset
        with patch('backend.session.cleanup_stale_auggie_processes'):
            result = SessionManager.reset(workspace)
        
        # Should return False and session should still exist
        assert result == False
        with _lock:
            assert workspace in _sessions

    def test_reset_returns_true_when_not_in_use(self):
        """Test that reset returns True and removes session when not in use."""
        workspace = '/tmp/test-reset-not-in-use'
        
        # Create a session that's not in use
        session = AuggieSession(workspace)
        session.in_use = False
        session.process = None
        session.master_fd = None
        
        with _lock:
            _sessions[workspace] = session
        
        # Reset
        with patch('backend.session.cleanup_stale_auggie_processes'):
            result = SessionManager.reset(workspace)
        
        # Should return True and session should be removed
        assert result == True
        with _lock:
            assert workspace not in _sessions


class TestAuggieSessionId:
    """Test AuggieSession session_id for session persistence."""

    def test_session_init_with_session_id(self):
        """Test that session_id is stored on init."""
        session = AuggieSession('/tmp/test', model='test', session_id='abc-123')
        assert session.session_id == 'abc-123'

    def test_session_init_without_session_id(self):
        """Test that session_id defaults to None."""
        session = AuggieSession('/tmp/test')
        assert session.session_id is None


class TestSessionManagerWithSessionId:
    """Test SessionManager passes session_id correctly."""

    def setup_method(self):
        with _lock:
            _sessions.clear()

    def teardown_method(self):
        with _lock:
            for session in _sessions.values():
                try:
                    session.cleanup()
                except:
                    pass
            _sessions.clear()

    def test_get_or_create_stores_session_id(self):
        """Test that get_or_create stores session_id in new session."""
        workspace = '/tmp/test-session-id'

        with patch('backend.session.start_cleanup_thread'):
            session, is_new = SessionManager.get_or_create(
                workspace, model='test', session_id='xyz-789'
            )

        assert is_new is True
        assert session.session_id == 'xyz-789'

    def test_get_or_create_reuses_existing_session(self):
        """Test that get_or_create reuses existing session."""
        workspace = '/tmp/test-reuse'

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345

        existing = AuggieSession(workspace, session_id='existing-123')
        existing.process = mock_process

        with _lock:
            _sessions[workspace] = existing

        with patch('backend.session.start_cleanup_thread'):
            session, is_new = SessionManager.get_or_create(
                workspace, session_id='new-456'
            )

        assert is_new is False
        assert session.session_id == 'existing-123'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

