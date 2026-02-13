#!/usr/bin/env python3
"""
Compare auggie terminal output with API output.
"""

import os
import pty
import select
import time
import requests
import json
import re

# Test question that should produce 10+ lines of output
TEST_QUESTION = "List 10 different programming languages and briefly describe what each is best used for. Number them 1-10."

def strip_ansi(text):
    """Remove ANSI escape codes."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[PX^_].*?\x1b\\|\x1b.')
    return ansi_pattern.sub('', text)

def run_auggie_terminal(question, workspace="~"):
    """Run auggie in terminal and capture raw output."""
    print("=" * 60)
    print("RUNNING AUGGIE IN TERMINAL")
    print("=" * 60)
    
    workspace = os.path.expanduser(workspace)
    master_fd, slave_fd = pty.openpty()
    
    pid = os.fork()
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        os.chdir(workspace)
        os.execlp('auggie', 'auggie')
    
    os.close(slave_fd)
    
    all_output = ""
    
    # Wait for auggie to initialize
    print("[TERMINAL] Waiting for auggie to initialize...")
    start = time.time()
    while time.time() - start < 30:
        r, _, _ = select.select([master_fd], [], [], 0.5)
        if r:
            try:
                data = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                all_output += data
                if '›' in data or '>' in data:
                    print("[TERMINAL] Prompt detected, auggie ready")
                    break
            except:
                break
    
    # Send the question
    print(f"[TERMINAL] Sending question: {question[:50]}...")
    os.write(master_fd, question.encode('utf-8'))
    time.sleep(0.3)
    os.write(master_fd, b'\r')
    
    # Collect response
    print("[TERMINAL] Collecting response...")
    response_output = ""
    last_data = time.time()
    
    while time.time() - last_data < 10:  # 10 second timeout after last data
        r, _, _ = select.select([master_fd], [], [], 0.5)
        if r:
            try:
                data = os.read(master_fd, 4096).decode('utf-8', errors='replace')
                response_output += data
                last_data = time.time()
            except:
                break
    
    # Cleanup
    os.kill(pid, 9)
    os.close(master_fd)
    os.waitpid(pid, 0)
    
    clean_output = strip_ansi(response_output)
    
    print(f"\n[TERMINAL] Raw output length: {len(response_output)}")
    print(f"[TERMINAL] Clean output length: {len(clean_output)}")
    print("\n--- TERMINAL CLEAN OUTPUT ---")
    print(clean_output[-2000:] if len(clean_output) > 2000 else clean_output)
    print("--- END TERMINAL OUTPUT ---\n")
    
    return response_output, clean_output

def run_api_request(question, workspace="~"):
    """Call the chat API and capture output."""
    print("=" * 60)
    print("RUNNING API REQUEST")
    print("=" * 60)
    
    url = "http://localhost:5000/api/chat/stream"
    payload = {
        "message": question,
        "workspace": workspace
    }
    
    print(f"[API] Sending question: {question[:50]}...")
    
    all_events = []
    final_response = ""
    
    try:
        response = requests.post(url, json=payload, stream=True, timeout=120)
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    all_events.append(data)
                    
                    if data.get('type') == 'stream':
                        print(data.get('content', ''), end='', flush=True)
                    elif data.get('type') == 'response':
                        final_response = data.get('message', '')
                    elif data.get('type') == 'status':
                        print(f"\n[API STATUS] {data.get('message')}")
                    elif data.get('type') == 'error':
                        print(f"\n[API ERROR] {data.get('message')}")
    except Exception as e:
        print(f"[API] Error: {e}")
        return [], ""
    
    print(f"\n\n[API] Total events: {len(all_events)}")
    print(f"[API] Final response length: {len(final_response)}")
    print("\n--- API FINAL RESPONSE ---")
    print(final_response)
    print("--- END API RESPONSE ---\n")
    
    return all_events, final_response

def compare_outputs(terminal_clean, api_response):
    """Compare terminal and API outputs."""
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    
    print(f"Terminal clean length: {len(terminal_clean)}")
    print(f"API response length: {len(api_response)}")
    
    # Count lines
    terminal_lines = terminal_clean.strip().split('\n')
    api_lines = api_response.strip().split('\n')
    
    print(f"Terminal lines: {len(terminal_lines)}")
    print(f"API lines: {len(api_lines)}")
    
    # Check for embedded previous answers (look for repeated patterns)
    if api_response.count('1.') > 1 or api_response.count('1)') > 1:
        print("\n⚠️  WARNING: Possible embedded duplicate content detected!")

if __name__ == "__main__":
    print(f"Test question: {TEST_QUESTION}\n")
    
    # Run API first (since terminal will create a new session)
    api_events, api_response = run_api_request(TEST_QUESTION)
    
    # Uncomment to also run terminal comparison:
    # terminal_raw, terminal_clean = run_auggie_terminal(TEST_QUESTION)
    # compare_outputs(terminal_clean, api_response)

