import pytest
import sys
import os
import re
from typing import List, Optional, Pattern
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.terminal_agent.base import TerminalAgentConfig, TerminalAgentProvider
from backend.services.terminal_agent.processor import BaseStreamProcessor
from backend.models.stream_state import StreamState


class MockProvider(TerminalAgentProvider):

    def __init__(self):
        config = TerminalAgentConfig(name='mock', command='mock')
        super().__init__(config)

    def get_command(self, workspace: str, model: Optional[str] = None) -> List[str]:
        return ['mock']

    def get_prompt_patterns(self) -> List[Pattern]:
        return [re.compile(r'>\s*$')]

    def get_end_patterns(self) -> List[Pattern]:
        return [re.compile(r'>\s*$'), re.compile(r'Done\.')]

    def get_response_markers(self) -> List[str]:
        return ['●', '▸']

    def get_activity_indicators(self) -> List[str]:
        return ['Processing...', 'Thinking...']

    def get_skip_patterns(self) -> List[str]:
        return ['SKIP_THIS', 'Version 1.0']

    def sanitize_message(self, message: str) -> str:
        return message.replace('\n', ' ')

    def extract_response(self, raw_output: str, user_message: str) -> Optional[str]:
        return raw_output


class TestBaseStreamProcessor:

    def test_processor_initialization(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'test message')
        assert processor.user_message == 'test message'
        assert processor.message_short == 'test message'

    def test_processor_long_message_truncation(self):
        provider = MockProvider()
        long_message = 'a' * 50
        processor = BaseStreamProcessor(provider, long_message)
        assert len(processor.message_short) == 20

    def test_find_message_echo_found(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'hello world')
        output = 'Some prefix text hello world some suffix'
        pos = processor.find_message_echo(output, 'hello world')
        assert pos > 0
        assert output[pos:pos + 11] == 'hello world'

    def test_find_message_echo_not_found(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'hello world')
        output = 'This does not contain the message'
        pos = processor.find_message_echo(output, 'hello world')
        assert pos == -1

    def test_process_chunk_extracts_response(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'question')
        state = StreamState()
        state.mark_message_echo_found(0)

        output = '''question
● This is the response content
More content here
>'''

        result = processor.process_chunk(output, state)
        assert result is not None
        assert 'This is the response content' in result
        assert state.saw_response_marker is True

    def test_process_chunk_skips_patterns(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'question')
        state = StreamState()
        state.mark_message_echo_found(0)

        output = '''question
● Good content
SKIP_THIS should be skipped
More good content
Version 1.0 also skip
Final content
>'''

        result = processor.process_chunk(output, state)
        assert result is not None
        assert 'Good content' in result
        assert 'SKIP_THIS' not in result
        assert 'Version 1.0' not in result

    def test_check_end_pattern_not_started(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'question')
        state = StreamState()
        result = processor.check_end_pattern('some output >', state)
        assert result is False

    def test_check_end_pattern_with_activity(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'question')
        state = StreamState()
        state.mark_message_echo_found(0)
        state.mark_streaming_started()
        state.mark_response_marker_seen()

        output = 'Response content > Processing...'
        result = processor.check_end_pattern(output, state)
        assert result is False

    def test_multiple_response_markers(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'question')
        state = StreamState()
        state.mark_message_echo_found(0)

        output = '''question
● First line
▸ Second line with different marker
>'''

        result = processor.process_chunk(output, state)
        assert result is not None
        assert 'First line' in result


class TestProcessorStateInteraction:

    def test_marks_response_marker_seen(self):
        provider = MockProvider()
        processor = BaseStreamProcessor(provider, 'q')
        state = StreamState()
        state.mark_message_echo_found(0)

        output = '● Response content'
        processor.process_chunk(output, state)
        assert state.saw_response_marker is True

    def test_state_isolation(self):
        provider = MockProvider()
        processor1 = BaseStreamProcessor(provider, 'question1')
        processor2 = BaseStreamProcessor(provider, 'question2')
        state1 = StreamState()
        state2 = StreamState()

        state1.mark_message_echo_found(10)
        state1.mark_response_marker_seen()

        assert state2.saw_message_echo is False
        assert state2.saw_response_marker is False
        assert state2.output_start_pos == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

