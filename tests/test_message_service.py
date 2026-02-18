"""
Tests for message_service.py - Message schema transformation between API and DB formats.

Tests cover:
- generate_message_id: ID generation with unique suffixes
- db_to_api_format: Converting Q&A pairs to user/assistant messages
- api_to_db_format: Converting user/assistant messages to Q&A pairs
- add_question: Adding new questions to message list
- add_answer: Adding answers to existing questions
- get_message_count: Counting Q&A pairs
"""

import pytest
import sys
import os
from unittest.mock import patch
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services import message_service


class TestGenerateMessageId:
    """Test message ID generation."""

    def test_generate_message_id_basic(self):
        """Test basic ID generation includes chat_id and index."""
        msg_id = message_service.generate_message_id("chat123", 0)
        assert msg_id.startswith("chat123-0-")
        assert len(msg_id) > len("chat123-0-")

    def test_generate_message_id_unique(self):
        """Test that generated IDs are unique."""
        ids = [message_service.generate_message_id("chat", 0) for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_generate_message_id_different_indices(self):
        """Test IDs with different indices."""
        id1 = message_service.generate_message_id("chat", 0)
        id2 = message_service.generate_message_id("chat", 5)
        assert "chat-0-" in id1
        assert "chat-5-" in id2


class TestDbToApiFormat:
    """Test conversion from DB format to API format."""

    def test_empty_messages(self):
        """Test conversion of empty message list."""
        result = message_service.db_to_api_format("chat123", [])
        assert result == []

    def test_single_qa_pair(self):
        """Test conversion of single Q&A pair."""
        db_messages = [{
            'id': 'msg-1',
            'index': 0,
            'question': 'Hello?',
            'answer': 'Hi there!',
            'questionTime': '2024-01-01T10:00:00',
            'answerTime': '2024-01-01T10:00:05'
        }]
        result = message_service.db_to_api_format("chat123", db_messages)
        
        assert len(result) == 2
        assert result[0]['role'] == 'user'
        assert result[0]['content'] == 'Hello?'
        assert result[0]['messageId'] == 'msg-1'
        assert result[1]['role'] == 'assistant'
        assert result[1]['content'] == 'Hi there!'
        assert result[1]['messageId'] == 'msg-1'  # Same ID links Q&A

    def test_question_without_answer(self):
        """Test conversion when answer is missing (streaming in progress)."""
        db_messages = [{
            'id': 'msg-1',
            'index': 0,
            'question': 'What is AI?',
            'answer': None,
            'questionTime': '2024-01-01T10:00:00',
            'answerTime': None
        }]
        result = message_service.db_to_api_format("chat123", db_messages)
        
        assert len(result) == 1
        assert result[0]['role'] == 'user'
        assert result[0]['content'] == 'What is AI?'

    def test_multiple_qa_pairs(self):
        """Test conversion of multiple Q&A pairs."""
        db_messages = [
            {'id': 'msg-1', 'index': 0, 'question': 'Q1', 'answer': 'A1'},
            {'id': 'msg-2', 'index': 1, 'question': 'Q2', 'answer': 'A2'},
            {'id': 'msg-3', 'index': 2, 'question': 'Q3', 'answer': 'A3'},
        ]
        result = message_service.db_to_api_format("chat123", db_messages)
        
        assert len(result) == 6
        assert [m['role'] for m in result] == ['user', 'assistant'] * 3

    def test_partial_flag_preserved(self):
        """Test that partial flag is preserved for interrupted streaming."""
        db_messages = [{
            'id': 'msg-1',
            'index': 0,
            'question': 'Long question',
            'answer': 'Partial answer...',
            'partial': True
        }]
        result = message_service.db_to_api_format("chat123", db_messages)
        
        assert result[1]['partial'] == True

    def test_generates_id_if_missing(self):
        """Test that ID is generated if not present."""
        db_messages = [{
            'index': 0,
            'question': 'Test question',
            'answer': 'Test answer'
        }]
        result = message_service.db_to_api_format("chat123", db_messages)
        
        assert result[0]['messageId'] is not None
        assert result[0]['messageId'].startswith("chat123-")


class TestApiToDbFormat:
    """Test conversion from API format to DB format."""

    def test_empty_messages(self):
        """Test conversion of empty message list."""
        result = message_service.api_to_db_format("chat123", [])
        assert result == []

    def test_single_user_message(self):
        """Test conversion of single user message."""
        api_messages = [
            {'role': 'user', 'content': 'Hello'}
        ]
        result = message_service.api_to_db_format("chat123", api_messages)
        
        assert len(result) == 1
        assert result[0]['question'] == 'Hello'
        assert result[0]['answer'] is None
        assert result[0]['index'] == 0

    def test_user_assistant_pair(self):
        """Test conversion of user-assistant pair."""
        api_messages = [
            {'role': 'user', 'content': 'Hi', 'messageId': 'msg-1'},
            {'role': 'assistant', 'content': 'Hello!', 'messageId': 'msg-1'}
        ]
        result = message_service.api_to_db_format("chat123", api_messages)
        
        assert len(result) == 1
        assert result[0]['question'] == 'Hi'
        assert result[0]['answer'] == 'Hello!'
        assert result[0]['id'] == 'msg-1'

    def test_multiple_exchanges(self):
        """Test conversion of multiple user-assistant exchanges."""
        api_messages = [
            {'role': 'user', 'content': 'Q1'},
            {'role': 'assistant', 'content': 'A1'},
            {'role': 'user', 'content': 'Q2'},
            {'role': 'assistant', 'content': 'A2'},
        ]
        result = message_service.api_to_db_format("chat123", api_messages)
        
        assert len(result) == 2
        assert result[0]['question'] == 'Q1'
        assert result[0]['answer'] == 'A1'
        assert result[1]['question'] == 'Q2'
        assert result[1]['answer'] == 'A2'


class TestAddQuestion:
    """Test adding questions to message list."""

    def test_add_to_empty_list(self):
        """Test adding question to empty list."""
        messages = []
        messages, msg_id = message_service.add_question("chat123", messages, "First question")
        
        assert len(messages) == 1
        assert messages[0]['question'] == "First question"
        assert messages[0]['answer'] is None
        assert messages[0]['index'] == 0
        assert msg_id is not None

    def test_add_to_existing_list(self):
        """Test adding question to existing list."""
        messages = [{'id': 'msg-0', 'index': 0, 'question': 'Q0', 'answer': 'A0'}]
        messages, msg_id = message_service.add_question("chat123", messages, "Second question")
        
        assert len(messages) == 2
        assert messages[1]['question'] == "Second question"
        assert messages[1]['index'] == 1


class TestAddAnswer:
    """Test adding answers to existing questions."""

    def test_add_answer_to_existing_question(self):
        """Test adding answer to an existing question."""
        messages = [{
            'id': 'msg-1',
            'index': 0,
            'question': 'Test?',
            'answer': None,
            'answerTime': None
        }]
        messages = message_service.add_answer(messages, 'msg-1', 'Test answer!')
        
        assert messages[0]['answer'] == 'Test answer!'
        assert messages[0]['answerTime'] is not None

    def test_add_answer_nonexistent_id(self):
        """Test adding answer with non-existent message ID."""
        messages = [{'id': 'msg-1', 'question': 'Q', 'answer': None}]
        messages = message_service.add_answer(messages, 'nonexistent', 'Answer')
        
        # Original message unchanged
        assert messages[0]['answer'] is None


class TestGetMessageCount:
    """Test message counting."""

    def test_empty_list(self):
        """Test counting empty list."""
        assert message_service.get_message_count([]) == 0

    def test_with_messages(self):
        """Test counting messages."""
        messages = [{'id': '1'}, {'id': '2'}, {'id': '3'}]
        assert message_service.get_message_count(messages) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

