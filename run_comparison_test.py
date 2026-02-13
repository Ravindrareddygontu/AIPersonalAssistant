#!/usr/bin/env python3
"""
Run 5 questions through terminal auggie and API, save to DB, and compare outputs.
"""

import os
import pty
import select
import time
import requests
import json
import re
import uuid
from pymongo import MongoClient

# 5 distinct test questions
TEST_QUESTIONS = [
    "What files are in this folder? Just list the main files briefly.",
    "Is there any app running on port 5000? Just answer yes or no and what it is.",
    "What is the current date and time? Answer briefly.",
    "How many Python files are in this project? Give a number.",
    "What is the name of the main Flask app file in this project?",
]

WORKSPACE = os.path.dirname(os.path.abspath(__file__))

def strip_ansi(text):
    """Remove ANSI escape codes."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[PX^_].*?\x1b\\|\x1b.')
    return ansi_pattern.sub('', text)

def run_auggie_terminal(question, timeout=60):
    """Run auggie in terminal and capture raw output."""
    print(f"\n{'='*60}")
    print(f"TERMINAL: {question[:50]}...")
    print('='*60)
    
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()
    
    if pid == 0:
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        os.chdir(WORKSPACE)
        os.execlp('auggie', 'auggie')
    
    os.close(slave_fd)
    all_output = ""
    
    # Wait for initialization
    print("[TERMINAL] Waiting for auggie to initialize...")
    start = time.time()
    while time.time() - start < 30:
        r, _, _ = select.select([master_fd], [], [], 0.5)
        if r:
            try:
                data = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                all_output += data
                if '›' in data or '>' in data:
                    print("[TERMINAL] Prompt detected")
                    break
            except:
                break
    
    # Send question
    print(f"[TERMINAL] Sending: {question[:30]}...")
    os.write(master_fd, question.encode('utf-8'))
    time.sleep(0.3)
    os.write(master_fd, b'\r')
    
    # Collect response
    response_output = ""
    last_data = time.time()
    
    while time.time() - last_data < timeout:
        r, _, _ = select.select([master_fd], [], [], 0.5)
        if r:
            try:
                data = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                response_output += data
                last_data = time.time()
            except:
                break
        # Check if we got a full response (prompt appeared again)
        if time.time() - last_data > 5 and '›' in response_output[-500:]:
            break
    
    # Cleanup
    try:
        os.kill(pid, 9)
        os.close(master_fd)
        os.waitpid(pid, 0)
    except:
        pass
    
    clean = strip_ansi(response_output)
    print(f"[TERMINAL] Raw length: {len(response_output)}, Clean: {len(clean)}")
    return response_output, clean

def run_api_request(question, chat_id):
    """Call the chat API and get response."""
    print(f"\n{'='*60}")
    print(f"API: {question[:50]}...")
    print('='*60)
    
    url = "http://localhost:5000/api/chat/stream"
    payload = {"message": question, "workspace": WORKSPACE, "chatId": chat_id}
    
    all_content = ""
    try:
        resp = requests.post(url, json=payload, stream=True, timeout=120)
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    if data.get('type') == 'stream':
                        all_content += data.get('content', '')
                    elif data.get('type') == 'status':
                        print(f"[API STATUS] {data.get('message')}")
                    elif data.get('type') == 'error':
                        print(f"[API ERROR] {data.get('message')}")
    except Exception as e:
        print(f"[API] Error: {e}")
        return ""
    
    print(f"[API] Response length: {len(all_content)}")
    return all_content

def get_db_responses(chat_id):
    """Retrieve responses from MongoDB."""
    client = MongoClient('mongodb://localhost:27017')
    db = client['ai_chat_app']
    chat = db['chats'].find_one({'id': chat_id})
    client.close()
    return chat.get('messages', []) if chat else []

def main():
    print("\n" + "="*80)
    print("COMPARISON TEST: Terminal Auggie vs API (with DB storage)")
    print("="*80)
    
    # Create unique chat ID for API requests
    chat_id = str(uuid.uuid4())[:8]
    print(f"\nChat ID for API tests: {chat_id}")
    
    # Create the chat in MongoDB first
    client = MongoClient('mongodb://localhost:27017')
    db = client['ai_chat_app']
    db['chats'].insert_one({
        'id': chat_id,
        'title': 'Comparison Test',
        'messages': [],
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')
    })
    client.close()
    
    results = []
    
    for i, question in enumerate(TEST_QUESTIONS):
        print(f"\n\n{'#'*80}")
        print(f"# QUESTION {i+1}: {question}")
        print('#'*80)
        
        # Run through API (which saves to DB)
        api_response = run_api_request(question, chat_id)
        
        # Run through terminal 
        terminal_raw, terminal_clean = run_auggie_terminal(question)
        
        results.append({
            'question': question,
            'terminal_raw_len': len(terminal_raw),
            'terminal_clean_len': len(terminal_clean),
            'terminal_clean': terminal_clean[-500:] if len(terminal_clean) > 500 else terminal_clean,
            'api_response_len': len(api_response),
            'api_response': api_response[-500:] if len(api_response) > 500 else api_response,
        })
        
        time.sleep(2)  # Small delay between questions
    
    # Get all DB responses
    print("\n\n" + "="*80)
    print("DATABASE RESPONSES")
    print("="*80)
    
    db_messages = get_db_responses(chat_id)
    print(f"Total Q&A pairs in DB: {len(db_messages)}")
    
    for msg in db_messages:
        print(f"\n--- Message ID: {msg.get('id')} ---")
        print(f"Q: {msg.get('question', '')[:100]}...")
        print(f"A: {(msg.get('answer') or '')[:200]}...")
    
    # Summary comparison
    print("\n\n" + "="*80)
    print("COMPARISON SUMMARY")
    print("="*80)
    
    for i, r in enumerate(results):
        print(f"\nQ{i+1}: {r['question'][:50]}...")
        print(f"  Terminal clean len: {r['terminal_clean_len']}")
        print(f"  API response len: {r['api_response_len']}")
        print(f"  Terminal sample: {r['terminal_clean'][:100]}...")
        print(f"  API sample: {r['api_response'][:100]}...")

if __name__ == "__main__":
    main()

