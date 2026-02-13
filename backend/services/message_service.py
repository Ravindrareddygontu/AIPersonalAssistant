"""
Message Service - Handles message schema transformation between API and DB formats.

DB Schema (internal):
{
    messages: [
        {
            id: 'unique-id',
            index: 0,
            question: 'user question',
            answer: 'cleaned response (sent to frontend)',
            rawAnswer: 'original provider response',
            questionTime: 'ISO timestamp',
            answerTime: 'ISO timestamp'
        },
        ...
    ]
}

API Schema (frontend-facing):
{
    messages: [
        { role: 'user', content: '...', messageId: '...' },
        { role: 'assistant', content: '...', messageId: '...' },
        ...
    ]
}

"""

import hashlib
from datetime import datetime


def generate_message_id(chat_id, index, content):
    """Generate a unique message ID based on chat_id, index, and content hash."""
    content_str = content[:100] if content else ''
    content_hash = hashlib.md5(content_str.encode()).hexdigest()[:8]
    return f"{chat_id}-{index}-{content_hash}"


def db_to_api_format(chat_id, db_messages):
    """
    Convert DB format (Q&A pairs) to API format (separate user/assistant messages).
    
    Args:
        chat_id: The chat ID for generating message IDs
        db_messages: List of Q&A pair objects from DB
    
    Returns:
        List of separate user/assistant message objects for API
    """
    api_messages = []
    
    for qa_pair in db_messages:
        msg_id = qa_pair.get('id')
        index = qa_pair.get('index', len(api_messages) // 2)
        
        # Add user message (question)
        if qa_pair.get('question'):
            if not msg_id:
                msg_id = generate_message_id(chat_id, index, qa_pair['question'])
            api_messages.append({
                'role': 'user',
                'content': qa_pair['question'],
                'messageId': msg_id,
                'timestamp': qa_pair.get('questionTime')
            })
        
        # Add assistant message (answer)
        if qa_pair.get('answer'):
            api_messages.append({
                'role': 'assistant',
                'content': qa_pair['answer'],
                'messageId': msg_id,  # Same ID links Q&A together
                'timestamp': qa_pair.get('answerTime')
            })
    
    return api_messages


def api_to_db_format(chat_id, api_messages):
    """
    Convert API format (separate messages) to DB format (Q&A pairs).
    
    Args:
        chat_id: The chat ID
        api_messages: List of separate user/assistant message objects from API
    
    Returns:
        List of Q&A pair objects for DB storage
    """
    db_messages = []
    current_pair = None
    pair_index = 0
    
    for msg in api_messages:
        role = msg.get('role')
        content = msg.get('content', '')
        msg_id = msg.get('messageId')
        timestamp = msg.get('timestamp') or datetime.utcnow().isoformat()
        
        if role == 'user':
            # Start a new Q&A pair
            if not msg_id:
                msg_id = generate_message_id(chat_id, pair_index, content)
            current_pair = {
                'id': msg_id,
                'index': pair_index,
                'question': content,
                'answer': None,
                'questionTime': timestamp,
                'answerTime': None
            }
            db_messages.append(current_pair)
            pair_index += 1
        elif role == 'assistant' and current_pair:
            # Add answer to current Q&A pair
            current_pair['answer'] = content
            current_pair['answerTime'] = timestamp
    
    return db_messages


def get_message_count(db_messages):
    """Get the count of Q&A pairs (for display purposes)."""
    return len(db_messages)


def truncate_after_message_id(db_messages, message_id):
    """
    Remove all Q&A pairs after (and including) the one with the given message_id.
    
    Args:
        db_messages: List of Q&A pairs
        message_id: The ID of the message to truncate from
    
    Returns:
        Truncated list of Q&A pairs
    """
    for i, pair in enumerate(db_messages):
        if pair.get('id') == message_id:
            return db_messages[:i]
    return db_messages


def add_question(chat_id, db_messages, question_content):
    """
    Add a new question to the messages list.
    
    Returns:
        Tuple of (updated_messages, new_message_id)
    """
    index = len(db_messages)
    msg_id = generate_message_id(chat_id, index, question_content)
    
    new_pair = {
        'id': msg_id,
        'index': index,
        'question': question_content,
        'answer': None,
        'questionTime': datetime.utcnow().isoformat(),
        'answerTime': None
    }
    
    db_messages.append(new_pair)
    return db_messages, msg_id


def add_answer(db_messages, message_id, answer_content, raw_answer=None):
    """
    Add an answer to an existing question by message_id.

    Args:
        db_messages: List of Q&A pairs
        message_id: The ID of the Q&A pair to update
        answer_content: Cleaned response (sent to frontend)
        raw_answer: Original provider response

    Returns:
        Updated messages list
    """
    for pair in db_messages:
        if pair.get('id') == message_id:
            pair['answer'] = answer_content
            pair['rawAnswer'] = raw_answer if raw_answer else answer_content
            pair['answerTime'] = datetime.utcnow().isoformat()
            break
    return db_messages

