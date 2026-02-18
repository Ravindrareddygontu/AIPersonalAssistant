import uuid
from datetime import datetime


def generate_message_id(chat_id, index, content=None):
    unique_suffix = uuid.uuid4().hex[:8]
    return f"{chat_id}-{index}-{unique_suffix}"


def db_to_api_format(chat_id, db_messages):
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
                'timestamp': qa_pair.get('answerTime'),
                'partial': qa_pair.get('partial', False)  # True if streaming was interrupted
            })
    
    return api_messages


def api_to_db_format(chat_id, api_messages):
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
    return len(db_messages)


def add_question(chat_id, db_messages, question_content):
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


def add_answer(db_messages, message_id, answer_content):
    for pair in db_messages:
        if pair.get('id') == message_id:
            pair['answer'] = answer_content
            pair['answerTime'] = datetime.utcnow().isoformat()
            break
    return db_messages

