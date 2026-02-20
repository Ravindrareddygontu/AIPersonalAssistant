import pytest
import sys
import os
import re
from typing import List, Optional, Pattern
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.terminal_agent.base import TerminalAgentConfig, TerminalAgentProvider
from backend.services.terminal_agent.session import TerminalSession


class MockProvider(TerminalAgentProvider):

    def __init__(self):
        config = TerminalAgentConfig(name='mock', command='echo')
        super().__init__(config)

    def get_command(self, workspace: str, model: Optional[str] = None, session_id: Optional[str] = None) -> List[str]:
        return ['echo', 'test']

    def get_prompt_patterns(self) -> List[Pattern]:
        return [re.compile(r'>\s*$'), re.compile(r'\$\s*$')]

    def get_end_patterns(self) -> List[Pattern]:
        return [re.compile(r'Done')]

    def get_response_markers(self) -> List[str]:
        return ['●']

    def get_activity_indicators(self) -> List[str]:
        return []

    def get_skip_patterns(self) -> List[str]:
        return []

    def sanitize_message(self, message: str) -> str:
        return message

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        return raw_output


class TestTerminalSession:

    def test_session_initialization(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp', 'test-model')
        assert session.provider == provider
        assert session.workspace == '/tmp'
        assert session.model == 'test-model'
        assert session.initialized is False
        assert session.in_use is False

    def test_session_key(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/home/user', 'v1')
        assert session.session_key == 'mock:/home/user:v1'

    def test_session_key_default_model(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        assert 'default' in session.session_key

    def test_is_alive_no_process(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        assert session.is_alive() is False

    def test_cleanup_no_process(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        session.cleanup()
        assert session.process is None
        assert session.master_fd is None
        assert session.initialized is False

    def test_write_no_fd(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        result = session.write(b'test')
        assert result is False

    def test_read_no_fd(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        result = session.read()
        assert result == ''

    def test_drain_output_no_fd(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        result = session.drain_output()
        assert result == ''

    def test_wait_for_prompt_no_fd(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        success, output = session.wait_for_prompt(timeout=0.1)
        assert success is False
        assert output == ''


class TestTerminalSessionWithMocks:

    @patch('backend.services.terminal_agent.session.pty.openpty')
    @patch('backend.services.terminal_agent.session.Popen')
    @patch('backend.services.terminal_agent.session.os.close')
    @patch('backend.services.terminal_agent.session.fcntl.ioctl')
    def test_start_success(self, mock_ioctl, mock_close, mock_popen, mock_openpty):
        mock_openpty.return_value = (10, 11)
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')

        with patch.object(session, '_set_nonblocking'):
            result = session.start()

        assert result is True
        assert session.master_fd == 10
        assert session.process == mock_process
        mock_close.assert_called_once_with(11)

    @patch('backend.services.terminal_agent.session.pty.openpty')
    def test_start_failure(self, mock_openpty):
        mock_openpty.side_effect = OSError('PTY creation failed')

        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        result = session.start()

        assert result is False
        assert session.master_fd is None

    def test_is_alive_with_running_process(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        session.process = MagicMock()
        session.process.poll.return_value = None
        assert session.is_alive() is True

    def test_is_alive_with_terminated_process(self):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        session.process = MagicMock()
        session.process.poll.return_value = 0
        assert session.is_alive() is False

    @patch('backend.services.terminal_agent.session.os.write')
    def test_write_success(self, mock_write):
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        session.master_fd = 10

        result = session.write(b'hello')
        assert result is True
        mock_write.assert_called_once_with(10, b'hello')

    @patch('backend.services.terminal_agent.session.os.write')
    def test_write_broken_pipe(self, mock_write):
        mock_write.side_effect = BrokenPipeError()
        provider = MockProvider()
        session = TerminalSession(provider, '/tmp')
        session.master_fd = 10

        result = session.write(b'hello')
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

