import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestSessionExists:

    def test_session_exists_true(self):
        from backend.services.auggie.session_tracker import session_exists
        
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id = "test-session-123"
            session_file = os.path.join(tmpdir, f"{session_id}.json")
            with open(session_file, 'w') as f:
                json.dump({"sessionId": session_id}, f)
            
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                assert session_exists(session_id) is True

    def test_session_exists_false(self):
        from backend.services.auggie.session_tracker import session_exists
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                assert session_exists("nonexistent-session") is False

    def test_session_exists_empty_id(self):
        from backend.services.auggie.session_tracker import session_exists
        
        assert session_exists("") is False
        assert session_exists(None) is False


class TestGetLatestSessionForWorkspace:

    def test_finds_session_for_workspace(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = "/home/user/project"
            session_id = "abc-123-def"
            
            session_data = {
                "sessionId": session_id,
                "chatHistory": [{
                    "exchange": {
                        "request_nodes": [{
                            "type": 4,
                            "ide_state_node": {
                                "workspace_folders": [{"folder_root": workspace}]
                            }
                        }]
                    }
                }]
            }
            
            session_file = os.path.join(tmpdir, f"{session_id}.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
            
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace(workspace)
                assert result == session_id

    def test_no_session_for_workspace(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = "/home/user/other-project"
            session_data = {
                "sessionId": "xyz-789",
                "chatHistory": [{
                    "exchange": {
                        "request_nodes": [{
                            "type": 4,
                            "ide_state_node": {
                                "workspace_folders": [{"folder_root": "/different/path"}]
                            }
                        }]
                    }
                }]
            }
            
            session_file = os.path.join(tmpdir, "xyz-789.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
            
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace(workspace)
                assert result is None

    def test_returns_most_recent_session(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace
        import time
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = "/home/user/project"
            
            for i, session_id in enumerate(["old-session", "new-session"]):
                session_data = {
                    "sessionId": session_id,
                    "chatHistory": [{
                        "exchange": {
                            "request_nodes": [{
                                "type": 4,
                                "ide_state_node": {
                                    "workspace_folders": [{"folder_root": workspace}]
                                }
                            }]
                        }
                    }]
                }
                
                session_file = os.path.join(tmpdir, f"{session_id}.json")
                with open(session_file, 'w') as f:
                    json.dump(session_data, f)
                time.sleep(0.05)
            
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace(workspace)
                assert result == "new-session"

    def test_filters_by_after_time(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace
        import time
        
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = "/home/user/project"
            session_data = {
                "sessionId": "old-session",
                "chatHistory": [{
                    "exchange": {
                        "request_nodes": [{
                            "type": 4,
                            "ide_state_node": {
                                "workspace_folders": [{"folder_root": workspace}]
                            }
                        }]
                    }
                }]
            }
            
            session_file = os.path.join(tmpdir, "old-session.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
            
            after_time = datetime.now() + timedelta(seconds=10)

            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace(workspace, after_time)
                assert result is None

    def test_handles_missing_directory(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace

        with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', '/nonexistent/path'):
            result = get_latest_session_for_workspace("/home/user/project")
            assert result is None

    def test_handles_malformed_json(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace

        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = os.path.join(tmpdir, "bad-session.json")
            with open(session_file, 'w') as f:
                f.write("not valid json {{{")

            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace("/home/user/project")
                assert result is None

    def test_normalizes_workspace_paths(self):
        from backend.services.auggie.session_tracker import get_latest_session_for_workspace

        with tempfile.TemporaryDirectory() as tmpdir:
            session_data = {
                "sessionId": "session-123",
                "chatHistory": [{
                    "exchange": {
                        "request_nodes": [{
                            "type": 4,
                            "ide_state_node": {
                                "workspace_folders": [{"folder_root": "/home/user/project/"}]
                            }
                        }]
                    }
                }]
            }

            session_file = os.path.join(tmpdir, "session-123.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f)

            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_latest_session_for_workspace("/home/user/project")
                assert result == "session-123"


class TestGetSessionWorkspace:

    def test_gets_workspace_from_session(self):
        from backend.services.auggie.session_tracker import get_session_workspace

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = "/home/user/myproject"
            session_id = "session-456"
            session_data = {
                "sessionId": session_id,
                "chatHistory": [{
                    "exchange": {
                        "request_nodes": [{
                            "type": 4,
                            "ide_state_node": {
                                "workspace_folders": [{"folder_root": workspace}]
                            }
                        }]
                    }
                }]
            }

            session_file = os.path.join(tmpdir, f"{session_id}.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f)

            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_session_workspace(session_id)
                assert result == workspace

    def test_returns_none_for_missing_session(self):
        from backend.services.auggie.session_tracker import get_session_workspace

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('backend.services.auggie.session_tracker.AUGMENT_SESSIONS_DIR', tmpdir):
                result = get_session_workspace("nonexistent")
                assert result is None

    def test_returns_none_for_empty_id(self):
        from backend.services.auggie.session_tracker import get_session_workspace

        assert get_session_workspace("") is None
        assert get_session_workspace(None) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

