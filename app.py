"""
AI Chat Application - Flask Backend
A beautiful web interface for chatting with AI using Augment Code CLI (auggie)

This app sends your questions to auggie CLI, which can:
- Read and edit files in your project
- Run commands
- Answer questions about your codebase
- Do everything Augment can do in your IDE!
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import subprocess
import os
import json
import re
import threading
import time
import sys
import pty
import select

app = Flask(__name__)

# Store settings - workspace is the directory auggie will work in
settings = {
    'workspace': os.path.expanduser('~'),  # Default to home directory
}

# Store active auggie PTY sessions per workspace
auggie_sessions = {}
session_lock = threading.Lock()


class AuggieSession:
    """Manages a persistent auggie session using PTY"""
    def __init__(self, workspace):
        self.workspace = workspace
        self.process = None
        self.master_fd = None
        self.last_used = time.time()
        self.lock = threading.Lock()
        self.initialized = False
        self.last_response = ""  # Track last response to avoid repeating it
        self.last_message = ""   # Track last user message

    def start(self):
        """Start the auggie process"""
        import signal

        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env['TERM'] = 'xterm-256color'
        env['AUGMENT_WORKSPACE'] = self.workspace
        env['COLUMNS'] = '200'
        env['LINES'] = '100'

        self.process = subprocess.Popen(
            ['auggie'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.workspace,
            env=env,
            preexec_fn=os.setsid
        )
        os.close(slave_fd)
        self.master_fd = master_fd
        self.last_used = time.time()
        return self.master_fd

    def is_alive(self):
        """Check if the process is still running"""
        if self.process is None:
            return False
        return self.process.poll() is None

    def cleanup(self):
        """Clean up the session"""
        import signal
        if self.process:
            try:
                os.kill(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=2)
            except:
                try:
                    os.kill(self.process.pid, signal.SIGKILL)
                except:
                    pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
        self.process = None
        self.master_fd = None
        self.initialized = False


def get_or_create_session(workspace):
    """Get existing session or create a new one"""
    with session_lock:
        if workspace in auggie_sessions:
            session = auggie_sessions[workspace]
            if session.is_alive():
                session.last_used = time.time()
                return session, False  # False = not new
            else:
                # Session died, clean up and create new
                session.cleanup()

        # Create new session
        session = AuggieSession(workspace)
        auggie_sessions[workspace] = session
        return session, True  # True = new session


def cleanup_old_sessions():
    """Clean up sessions that haven't been used in 10 minutes"""
    with session_lock:
        current_time = time.time()
        to_remove = []
        for workspace, session in auggie_sessions.items():
            if current_time - session.last_used > 600:  # 10 minutes
                session.cleanup()
                to_remove.append(workspace)
        for workspace in to_remove:
            del auggie_sessions[workspace]


@app.route('/')
def index():
    """Render the main chat interface"""
    return render_template('index.html')


@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save workspace settings"""
    data = request.json
    if data.get('workspace'):
        workspace = data['workspace']
        # Expand ~ to home directory
        workspace = os.path.expanduser(workspace)
        if os.path.isdir(workspace):
            settings['workspace'] = workspace
            return jsonify({'status': 'success', 'workspace': workspace})
        else:
            return jsonify({'status': 'error', 'error': f'Directory not found: {workspace}'})
    return jsonify({'status': 'success'})


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current settings"""
    return jsonify(settings)


@app.route('/api/session/reset', methods=['POST'])
def reset_session():
    """Reset the auggie session for a workspace (starts fresh context)"""
    data = request.json or {}
    workspace = data.get('workspace', settings['workspace'])
    workspace = os.path.expanduser(workspace)

    with session_lock:
        if workspace in auggie_sessions:
            auggie_sessions[workspace].cleanup()
            del auggie_sessions[workspace]

    return jsonify({'status': 'success', 'message': 'Session reset'})


# Chat history storage
CHATS_DIR = os.path.join(os.path.dirname(__file__), 'chats')
os.makedirs(CHATS_DIR, exist_ok=True)


def get_chat_filepath(chat_id):
    """Get the filepath for a chat"""
    return os.path.join(CHATS_DIR, f'{chat_id}.json')


@app.route('/api/chats', methods=['GET'])
def list_chats():
    """List all saved chats"""
    chats = []
    for filename in os.listdir(CHATS_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(CHATS_DIR, filename)
            try:
                with open(filepath, 'r') as f:
                    chat_data = json.load(f)
                    chats.append({
                        'id': chat_data.get('id'),
                        'title': chat_data.get('title', 'Untitled'),
                        'created_at': chat_data.get('created_at'),
                        'updated_at': chat_data.get('updated_at'),
                        'message_count': len(chat_data.get('messages', []))
                    })
            except:
                pass
    # Sort by updated_at descending
    chats.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return jsonify(chats)


@app.route('/api/chats', methods=['POST'])
def create_chat():
    """Create a new chat"""
    import uuid
    from datetime import datetime

    chat_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    chat_data = {
        'id': chat_id,
        'title': 'New Chat',
        'created_at': now,
        'updated_at': now,
        'messages': [],
        'workspace': settings['workspace']
    }

    filepath = get_chat_filepath(chat_id)
    with open(filepath, 'w') as f:
        json.dump(chat_data, f, indent=2)

    return jsonify(chat_data)


@app.route('/api/chats/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Get a specific chat"""
    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404

    with open(filepath, 'r') as f:
        chat_data = json.load(f)
    return jsonify(chat_data)


@app.route('/api/chats/<chat_id>', methods=['PUT'])
def update_chat(chat_id):
    """Update a chat (add messages, rename, etc.)"""
    from datetime import datetime

    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404

    with open(filepath, 'r') as f:
        chat_data = json.load(f)

    data = request.json

    # Update title if provided
    if 'title' in data:
        chat_data['title'] = data['title']

    # Update messages if provided
    if 'messages' in data:
        chat_data['messages'] = data['messages']

    # Auto-generate title from first user message if still "New Chat"
    if chat_data['title'] == 'New Chat' and chat_data['messages']:
        for msg in chat_data['messages']:
            if msg.get('role') == 'user':
                # Use first 50 chars of first user message as title
                title = msg.get('content', '')[:50]
                if len(msg.get('content', '')) > 50:
                    title += '...'
                chat_data['title'] = title
                break

    chat_data['updated_at'] = datetime.now().isoformat()

    with open(filepath, 'w') as f:
        json.dump(chat_data, f, indent=2)

    return jsonify(chat_data)


@app.route('/api/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """Delete a chat"""
    filepath = get_chat_filepath(chat_id)
    if not os.path.exists(filepath):
        return jsonify({'error': 'Chat not found'}), 404

    os.remove(filepath)
    return jsonify({'status': 'deleted', 'id': chat_id})


@app.route('/api/chats/clear', methods=['DELETE'])
def clear_all_chats():
    """Delete all chats"""
    for filename in os.listdir(CHATS_DIR):
        if filename.endswith('.json'):
            os.remove(os.path.join(CHATS_DIR, filename))
    return jsonify({'status': 'cleared'})


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages using Augment CLI (auggie)"""
    data = request.json
    message = data.get('message', '')
    workspace = data.get('workspace', settings['workspace'])

    # Expand ~ to home directory
    workspace = os.path.expanduser(workspace)

    try:
        response = call_auggie(message, workspace)
        return jsonify({'response': response, 'workspace': workspace})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """
    Stream chat response with real-time status updates using Server-Sent Events.
    Uses PTY to interact with auggie's interactive TUI.
    """
    data = request.json
    message = data.get('message', '')
    workspace = data.get('workspace', settings['workspace'])
    workspace = os.path.expanduser(workspace)

    def generate():
        import signal

        # Send initial padding to prime browser buffer (browsers often buffer first ~1-2KB)
        yield ": " + " " * 2048 + "\n\n"

        try:
            if not os.path.isdir(workspace):
                workspace_path = os.path.expanduser('~')
            else:
                workspace_path = workspace

            # Get or create persistent session
            session, is_new = get_or_create_session(workspace_path)

            # Acquire session lock to prevent concurrent access
            with session.lock:
                master_fd = None

                if is_new or not session.initialized:
                    # New session - need to start auggie
                    yield f"data: {json.dumps({'type': 'status', 'message': 'Starting Augment...'})}\n\n"

                    master_fd = session.start()

                    yield f"data: {json.dumps({'type': 'status', 'message': 'Waiting for Augment to initialize...'})}\n\n"

                    # Wait for initial prompt
                    start_time = time.time()
                    initial_output = ""
                    prompt_ready = False

                    while time.time() - start_time < 15:
                        ready, _, _ = select.select([master_fd], [], [], 0.3)
                        if ready:
                            try:
                                chunk = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                                if chunk:
                                    initial_output += chunk
                                    if '›' in chunk:
                                        prompt_ready = True
                                        time.sleep(0.5)
                                        # Drain any remaining output
                                        while True:
                                            r, _, _ = select.select([master_fd], [], [], 0.2)
                                            if r:
                                                try:
                                                    extra = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                                                    initial_output += extra
                                                except:
                                                    break
                                            else:
                                                break
                                        break
                            except OSError:
                                break

                    if not prompt_ready:
                        session.cleanup()
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to start Augment'})}\n\n"
                        return

                    session.initialized = True
                else:
                    # Existing session - just use it
                    yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting...'})}\n\n"
                    master_fd = session.master_fd

                    # Drain any pending output from previous interaction
                    drain_start = time.time()
                    while time.time() - drain_start < 0.5:
                        r, _, _ = select.select([master_fd], [], [], 0.1)
                        if r:
                            try:
                                _ = os.read(master_fd, 8192)  # Discard old output
                            except:
                                break
                        else:
                            break

                yield f"data: {json.dumps({'type': 'status', 'message': 'Sending your message...'})}\n\n"

                # Send message
                os.write(master_fd, message.encode('utf-8'))
                time.sleep(0.1)
                os.write(master_fd, b'\r')
                time.sleep(0.1)
                os.write(master_fd, b'\n')

                # Track output
                all_output = ""
                last_data_time = time.time()
                message_sent_time = time.time()
                saw_message_echo = False
                saw_response_marker = False
                streaming_started = False
                last_streamed_content = ""

                yield f"data: {json.dumps({'type': 'status', 'message': 'Waiting for AI response...'})}\n\n"

                while time.time() - message_sent_time < 300:
                    # Use very short timeout for real-time streaming
                    ready, _, _ = select.select([master_fd], [], [], 0.01)
                    if ready:
                        try:
                            chunk = os.read(master_fd, 512).decode('utf-8', errors='ignore')
                            if chunk:
                                all_output += chunk
                                last_data_time = time.time()

                                clean_output = strip_ansi(all_output)

                                # Check if our message was echoed back
                                if message in clean_output and not saw_message_echo:
                                    saw_message_echo = True
                                    yield f"data: {json.dumps({'type': 'status', 'message': 'Processing your request...'})}\n\n"

                                if saw_message_echo:
                                    # Extract response content
                                    current_response = extract_new_response_content(
                                        clean_output,
                                        message,
                                        session.last_response if session else ""
                                    )

                                    if current_response:
                                        # Stream new content
                                        if len(current_response) > len(last_streamed_content):
                                            if not streaming_started:
                                                streaming_started = True
                                                saw_response_marker = True
                                                yield f"data: {json.dumps({'type': 'stream_start'})}\n\n"

                                            # Send only the NEW content (delta)
                                            new_text = current_response[len(last_streamed_content):]
                                            if new_text and len(new_text.strip()) > 2:
                                                # Stream word by word for smooth effect
                                                words = new_text.split(' ')
                                                for i, word in enumerate(words):
                                                    if word or i < len(words) - 1:
                                                        content = word + (' ' if i < len(words) - 1 else '')
                                                        if content and len(content.strip()) > 0:
                                                            yield f"data: {json.dumps({'type': 'stream', 'content': content})}\n\n"
                                                            yield ": padding" + " " * 2048 + "\n\n"
                                                            time.sleep(0.015)
                                            last_streamed_content = current_response

                                    # Check for completion (new prompt appearing)
                                    if streaming_started and (re.search(r'│ ›\s*│', clean_output) or re.search(r'╰─+╯', clean_output[-300:] if len(clean_output) > 300 else clean_output)):
                                        time.sleep(0.3)
                                        # Drain remaining output
                                        while True:
                                            r, _, _ = select.select([master_fd], [], [], 0.2)
                                            if r:
                                                try:
                                                    extra = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                                                    all_output += extra
                                                except:
                                                    pass
                                            else:
                                                break
                                        break
                        except OSError:
                            break
                    else:
                        elapsed_no_data = time.time() - last_data_time
                        wait_threshold = 5 if saw_response_marker else 15
                        if saw_response_marker and elapsed_no_data > wait_threshold:
                            break
                        if saw_message_echo and not saw_response_marker and (time.time() - message_sent_time) > 120:
                            break

                # Extract final response
                response_text = extract_auggie_response(all_output, message)

                # Filter out previous response if present
                if response_text and session.last_response:
                    prev_resp_normalized = session.last_response.strip()
                    if response_text.startswith(prev_resp_normalized):
                        response_text = response_text[len(prev_resp_normalized):].lstrip('\n')
                    elif prev_resp_normalized in response_text:
                        idx = response_text.find(prev_resp_normalized)
                        response_text = response_text[idx + len(prev_resp_normalized):].lstrip('\n')

                # Send stream_end
                if streaming_started:
                    yield f"data: {json.dumps({'type': 'stream_end', 'content': ''})}\n\n"
                elif response_text:
                    # No streaming started, send all at once
                    yield f"data: {json.dumps({'type': 'stream_start'})}\n\n"
                    words = response_text.split(' ')
                    for i, word in enumerate(words):
                        if word or i < len(words) - 1:
                            content = word + (' ' if i < len(words) - 1 else '')
                            if content:
                                yield f"data: {json.dumps({'type': 'stream', 'content': content})}\n\n"
                                yield ": " + " " * 512 + "\n\n"
                                time.sleep(0.02)
                    yield f"data: {json.dumps({'type': 'stream_end', 'content': ''})}\n\n"

                # Update session state
                session.last_used = time.time()
                session.last_message = message
                session.last_response = response_text or ""

                # Clean up old sessions
                cleanup_old_sessions()

                if not response_text:
                    response_text = "I processed your request but couldn't extract the response. Please try again."

                yield f"data: {json.dumps({'type': 'response', 'message': response_text, 'workspace': workspace_path})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    response = Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable nginx buffering if present
    response.headers['Connection'] = 'keep-alive'
    response.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
    return response


def strip_ansi(text):
    """Remove ANSI escape codes from text"""
    # Comprehensive ANSI escape sequence patterns
    ansi_patterns = [
        r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])',  # Standard ANSI
        r'\x1B\[[0-9;]*[a-zA-Z]',  # CSI sequences
        r'\x1B\][^\x07]*\x07',  # OSC sequences
        r'\x1B[PX^_][^\x1B]*\x1B\\',  # DCS, SOS, PM, APC sequences
        r'\x1B.',  # Any remaining escape + char
    ]
    result = text
    for pattern in ansi_patterns:
        result = re.sub(pattern, '', result)
    return result


def extract_print_mode_response(raw_output):
    """
    Extract the AI response from auggie --print mode output.

    In print mode, the output is linear and contains:
    - Action lines starting with ● (tool usage)
    - Sub-action lines starting with ⎿ (tool results)
    - The final response text
    """
    text = strip_ansi(raw_output)

    # Remove control characters but keep newlines
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    lines = text.split('\n')
    response_lines = []
    in_response = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines at the start
        if not stripped and not in_response:
            continue

        # Skip action/tool lines (these are status messages)
        if stripped.startswith('●') or stripped.startswith('•'):
            continue
        if stripped.startswith('⎿') or stripped.startswith('↳') or stripped.startswith('└'):
            continue

        # Skip banner/header lines
        skip_patterns = [
            '▇', '╗', '╔', '═', '║', '╚', '╝',
            'Version ', 'Get started', 'For automation',
            'Indexing disabled', 'working directory'
        ]
        if any(p in stripped for p in skip_patterns):
            continue

        # This looks like actual response content
        if stripped:
            in_response = True
            response_lines.append(line)
        elif in_response:
            # Keep empty lines within the response
            response_lines.append(line)

    response_text = '\n'.join(response_lines).strip()

    # Clean up excessive whitespace
    response_text = re.sub(r'\n{3,}', '\n\n', response_text)

    return response_text


def extract_new_response_content(clean_output, current_message, previous_response):
    """
    Extract ONLY new response content, filtering out previous responses.

    This handles auggie's screen redrawing behavior where the entire
    conversation history is redrawn on each update.

    The key insight: We need to find the LAST occurrence of the current message
    being submitted (with › marker), and extract content AFTER that point only.
    The submitted format is: "› message" followed by response markers (~, ●).

    IMPORTANT: When looking for the current message, we must find it in
    SUBMITTED format (› message) because content in the input box (│ message │)
    appears BEFORE the previous Q&A pair in the terminal redraw.

    Args:
        clean_output: The ANSI-stripped terminal output
        current_message: The current user message
        previous_response: The previous response text (to filter out)

    Returns:
        The new response content only
    """
    # UI elements to skip
    skip_patterns = [
        'You can ask questions',
        'Use Ctrl + Enter',
        'Use vim mode',
        'For automation',
        'Indexing disabled',
        'working directory',
        'To get the most out',
        'from a project directory',
        'Ctrl+P to enhance',
        'Ctrl+S to stash',
        'Claude Opus',
        'Version 0.',
        'commit ',
        '@veefin.com',
        '@gmail.com',
        'ravindrar@',
        'Processing response...',
        'esc to interrupt',
    ]

    # Clean up any remaining ANSI code fragments (numeric codes without escape char)
    clean_output = re.sub(r'\d+;2;\d+', '', clean_output)
    # Clean up braille spinner characters
    clean_output = re.sub(r'[\u2800-\u28FF]', '', clean_output)

    # Find the LAST occurrence of the SUBMITTED current message ONLY
    # The submitted format is "› message" - we MUST find this format
    # DO NOT fall back to searching for the message alone, because that
    # could find it in the input box (│ message │) which appears BEFORE
    # the previous Q&A pair in the terminal redraw
    msg_short = current_message[:30] if len(current_message) > 30 else current_message

    # ONLY look for the submitted format
    # Based on debug logs, the format can be:
    # - "› message" (on same line)
    # - "› \n message" (with newline between)
    # - "› \n  message" (with newline and spaces)
    # We'll use regex to handle all variations

    # Find all occurrences of › followed by the message (with optional whitespace/newlines)
    # We need to find SUBMITTED messages, NOT input box messages
    # Input box format: "│ › message │" or "│ › message" (has │ nearby)
    # Submitted format: "› message" on its own line (no │ nearby)
    pattern = r'›\s*' + re.escape(msg_short)
    matches = list(re.finditer(pattern, clean_output))

    # Filter out input box matches - look for SUBMITTED format only
    # A submitted message line doesn't have │ character after the message
    last_submitted_pos = -1
    for match in reversed(matches):
        match_end = match.end()
        # Check if this is in an input box (has │ after message on same line)
        # Look at next ~80 chars (line might have padding)
        lookahead = clean_output[match_end:match_end+100] if match_end < len(clean_output) else ""
        first_newline = lookahead.find('\n')
        if first_newline > 0:
            lookahead = lookahead[:first_newline]

        # If there's no │ or ╰ in the rest of the line, it's a submitted message
        if '│' not in lookahead and '╰' not in lookahead:
            last_submitted_pos = match.start()
            break
        # Also check: if followed by response markers (~, ●), it's definitely submitted
        elif '~' in lookahead or '●' in lookahead:
            last_submitted_pos = match.start()
            break

    # Debug logging moved to after extraction

    # If NOT found in submitted format, return empty - message not yet processed
    # This is crucial: we MUST wait until the message is submitted and appears
    # with the › marker before extracting any response content
    if last_submitted_pos < 0:
        return ""

    # Get content AFTER the submitted message position
    after_message = clean_output[last_submitted_pos:]

    # Find all response sections - content after ~ (thinking) or ● (response)
    # But ONLY in the after_message portion
    # IMPORTANT: Response markers in auggie TUI appear at the START of a line with a leading space
    # Format: "\n ~ thinking content" or "\n ● response content"
    # This distinguishes them from UI elements like "Version ... ● email" or "[Claude] ~"
    response_parts = []

    # Pattern 1: Find thinking content (~ marker at start of line)
    # Match: newline + optional spaces + ~ + space + content
    for match in re.finditer(r'\n\s*~\s+(.+?)(?=\n\n|\n\s*●|\n\s*~|\n\s*›|╭|╰|$)', after_message, re.DOTALL):
        content = match.group(1).strip()
        # Clean up line continuations
        content = re.sub(r'\s+', ' ', content)
        if content and len(content) > 3:
            # Skip UI elements
            if not any(skip in content for skip in skip_patterns):
                response_parts.append(('thinking', content))

    # Pattern 2: Find response content (● marker at start of line)
    for match in re.finditer(r'\n\s*●\s+(.+?)(?=\n\n|\n\s*●|\n\s*~|\n\s*›|╭|╰|$)', after_message, re.DOTALL):
        content = match.group(1).strip()
        # Clean up line continuations
        content = re.sub(r'\s+', ' ', content)
        if content and len(content) > 3:
            # Skip UI elements
            if not any(skip in content for skip in skip_patterns):
                response_parts.append(('response', content))

    # Normalize previous response for comparison
    prev_normalized = re.sub(r'\s+', ' ', previous_response.strip()) if previous_response else ""

    # Build new response content (filtering out previous response content)
    new_content_parts = []
    seen_content = set()

    for part_type, content in response_parts:
        # Check if this content is part of the previous response
        content_normalized = re.sub(r'\s+', ' ', content)

        # Skip if this content appears in the previous response
        if prev_normalized and content_normalized in prev_normalized:
            continue

        # Skip if this is a duplicate of something we've already added
        if content_normalized in seen_content:
            continue
        seen_content.add(content_normalized)

        # Format based on type
        if part_type == 'thinking':
            new_content_parts.append(f"*{content}*")
        else:
            new_content_parts.append(content)

    # Debug logging
    with open('/tmp/auggie_extract_debug.log', 'a') as f:
        f.write(f"\n=== extract_new_response_content RESULT ===\n")
        f.write(f"Current message: {msg_short}\n")
        f.write(f"last_submitted_pos: {last_submitted_pos}\n")
        f.write(f"prev_normalized (first 100): {prev_normalized[:100] if prev_normalized else 'EMPTY'}\n")
        f.write(f"response_parts found: {len(response_parts)}\n")
        for i, (ptype, pcontent) in enumerate(response_parts[:3]):
            f.write(f"  Part {i} ({ptype}): {pcontent[:80]}...\n")
            # Check filtering
            pcontent_norm = re.sub(r'\s+', ' ', pcontent)
            in_prev = prev_normalized and pcontent_norm in prev_normalized
            f.write(f"    content in prev_normalized: {in_prev}\n")
        f.write(f"new_content_parts: {len(new_content_parts)}\n")
        result = '\n'.join(new_content_parts)
        f.write(f"Result (first 200): {result[:200]}\n")

    # Return combined new content
    return '\n'.join(new_content_parts)


def extract_streaming_content(after_message):
    """
    Extract response content for real-time streaming.
    This function receives content that is ALREADY after the user's message.
    """
    # Skip spinner/status lines at the very beginning
    if len(after_message) > 100:
        if 'Sending request' in after_message[:100] or 'esc to interrupt' in after_message[:100]:
            return ""

    # UI elements to skip
    skip_patterns = [
        'You can ask questions',
        'Use Ctrl + Enter',
        'Use vim mode',
        'For automation, use',
        'Indexing disabled',
        'Your working directory ~',
        'To get the most out of auggie',
        'from a project directory',
        'Ctrl+P to enhance',
        'Ctrl+S to stash',
        '[Claude Opus',
        'Version 0.1',
        '▇▇▇▇▇',
        '● ravindrar@',
        '● You can ask',
    ]

    # Process all lines after the user message
    lines = after_message.split('\n')
    response_lines = []
    in_response = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines at the start
        if not response_lines and not stripped:
            continue

        # Skip spinner/status lines
        if 'Sending request' in stripped or 'esc to interrupt' in stripped:
            continue
        if 'Processing response' in stripped:
            continue

        # Skip UI chrome (pure box-drawing characters)
        if re.match(r'^[╭╮╯╰│─╗╔║╚╝═\s]+$', stripped):
            continue
        if stripped.startswith('│ ›') or stripped == '│':
            continue

        # Skip known UI patterns
        if any(pattern in stripped for pattern in skip_patterns):
            continue

        # Handle thinking lines (~)
        if stripped.startswith('~'):
            content = stripped[1:].strip()
            if content and not any(pattern in content for pattern in skip_patterns):
                response_lines.append(f"*{content}*")
            in_response = True
            continue

        # Handle response/action lines (●)
        if stripped.startswith('●'):
            content = stripped[1:].strip()
            if content and not any(pattern in content for pattern in skip_patterns):
                response_lines.append(content)
            in_response = True
            continue

        # Handle sub-action lines (⎿)
        if stripped.startswith('⎿'):
            content = stripped[1:].strip()
            if content:
                response_lines.append(f"  ↳ {content}")
            in_response = True
            continue

        # Regular content lines - capture if we've seen any response marker
        if stripped and in_response:
            # Skip if it looks like UI
            if not any(pattern in stripped for pattern in skip_patterns):
                response_lines.append(stripped)

    return '\n'.join(response_lines)


def extract_auggie_response(raw_output, user_message):
    """
    Extract the actual AI response from auggie's TUI output.

    Auggie uses a full terminal UI with multiple screen refreshes.
    The response appears after the user's question marker (›).
    We need to find the LAST complete occurrence since terminal
    output contains multiple partial screen states.
    """
    # Remove ANSI codes
    text = strip_ansi(raw_output)

    # Remove common control characters but keep newlines
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # UI elements to skip (same as in extract_streaming_content)
    skip_patterns = [
        'You can ask questions',
        'Use Ctrl + Enter',
        'Use vim mode',
        'For automation',
        'Indexing disabled',
        'working directory',
        'To get the most out',
        'from a project directory',
        'Ctrl+P to enhance',
        'Ctrl+S to stash',
        'Claude Opus',
        'Version 0.',
        'commit ',
        '▇▇',  # Banner characters
        '╔', '╗', '╚', '╝', '═',  # Banner box
        '@veefin.com',
        '@gmail.com',
        'ravindrar@',
    ]

    # Strategy: Find all sections separated by horizontal lines,
    # then find the LAST one that contains both the user message
    # and actual response content (●)

    # Split by the horizontal line that separates conversations
    sections = re.split(r'─{10,}', text)

    # Find ALL sections containing both user message and response marker
    candidate_sections = []
    for section in sections:
        if user_message in section and '●' in section:
            candidate_sections.append(section)

    # Use the LAST complete section (most complete screen state)
    response_text = ""
    for section in reversed(candidate_sections):
        # Find the LAST occurrence of the user message in this section
        # This is crucial because auggie shows full conversation history
        last_msg_pos = section.rfind(user_message)
        if last_msg_pos < 0:
            continue

        # Only process content AFTER the last occurrence of the user message
        section_after_msg = section[last_msg_pos + len(user_message):]
        lines = section_after_msg.split('\n')

        response_lines = []
        found_response_marker = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines at the start
            if not response_lines and not stripped:
                continue

            if True:  # Always process (we're already after the message)
                # Stop at next input prompt box (but only after we have content)
                if found_response_marker and (stripped.startswith('╭') and '─' in stripped):
                    break

                # Skip empty lines at the start
                if not response_lines and not stripped:
                    continue

                # Skip spinner/status lines
                if 'Sending request' in stripped or 'esc to interrupt' in stripped:
                    continue
                if 'Processing response' in stripped:
                    continue

                # Skip known UI patterns
                if any(pattern in stripped for pattern in skip_patterns):
                    continue

                # Handle thinking lines (~)
                if stripped.startswith('~'):
                    content = stripped[1:].strip()
                    if content:
                        response_lines.append(f"*{content}*")  # Italicize thinking
                    continue

                # Handle response/action lines (●)
                if stripped.startswith('●'):
                    found_response_marker = True
                    content = stripped[1:].strip()
                    if content:
                        response_lines.append(content)
                    continue

                # Handle sub-action lines (⎿)
                if stripped.startswith('⎿'):
                    content = stripped[1:].strip()
                    if content:
                        response_lines.append(f"  ↳ {content}")
                    continue

                # Skip UI box chrome
                if stripped.startswith('╭') or stripped.startswith('╰'):
                    continue
                if stripped.startswith('│') and ('›' in stripped or len(stripped) < 5):
                    continue

                # Regular content lines (including tables, bullet points, etc.)
                # Only skip lines that are pure box-drawing
                if stripped and not re.match(r'^[╭╮╯╰│─╗╔║╚╝═\s]+$', stripped):
                    response_lines.append(stripped)

        if response_lines and found_response_marker:
            response_text = '\n'.join(response_lines)
            break

    # Fallback: Try to find response content after the LAST occurrence of user message
    if not response_text:
        # Find all occurrences of the user message with the prompt marker
        pattern = r'›\s*' + re.escape(user_message)
        matches = list(re.finditer(pattern, text))

        if matches:
            # Get content after the LAST occurrence
            last_match = matches[-1]
            start_pos = last_match.end()

            # Find content until next prompt box
            remaining = text[start_pos:]

            # Look for response marker ● and capture content after it
            response_match = re.search(r'●\s*([^╭╰]+)', remaining)
            if response_match:
                content = response_match.group(1).strip()
                # Clean up multi-line content
                lines = [l.strip() for l in content.split('\n') if l.strip()]
                # Filter out spinner/status lines
                lines = [l for l in lines if 'Sending request' not in l
                         and 'esc to interrupt' not in l
                         and 'Processing response' not in l]
                if lines:
                    response_text = '\n'.join(lines)

    # Clean up the response
    if response_text:
        # Remove any remaining UI elements
        response_text = re.sub(r'[╭╮╯╰│─╗╔║╚╝═]+', '', response_text)
        response_text = re.sub(r'\[Claude.*?\].*?~', '', response_text)
        response_text = re.sub(r'\? to show shortcuts.*', '', response_text)
        response_text = re.sub(r'Ctrl\+[A-Z].*', '', response_text)
        response_text = re.sub(r'\n{3,}', '\n\n', response_text)
        # Remove spinner lines (braille patterns and status messages)
        response_text = re.sub(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏].*?Sending request[^\n]*', '', response_text)
        response_text = re.sub(r'[^\n]*esc to interrupt[^\n]*', '', response_text)

        # Remove CLI footer/prompt text
        response_text = re.sub(r'Use vim mode with /vim.*', '', response_text, flags=re.IGNORECASE)
        response_text = re.sub(r"For automation.*auggie.*", '', response_text, flags=re.IGNORECASE)
        response_text = re.sub(r'auggie --print.*', '', response_text, flags=re.IGNORECASE)
        response_text = re.sub(r"'auggie --print.*", '', response_text, flags=re.IGNORECASE)
        response_text = re.sub(r'Copy\s*$', '', response_text, flags=re.MULTILINE)
        response_text = re.sub(r'^\s*Copy\s*$', '', response_text, flags=re.MULTILINE)

        # Remove any trailing prompt indicators
        response_text = re.sub(r'›\s*$', '', response_text)
        response_text = re.sub(r'\s*\n\s*›.*$', '', response_text)

        response_text = response_text.strip()

    # If response is ONLY spinner garbage (very short and contains only those phrases), return empty
    if response_text:
        stripped = response_text.replace('\n', ' ').strip()
        if len(stripped) < 100 and ('Sending request' in stripped or 'esc to interrupt' in stripped):
            response_text = ""

    return response_text


def call_auggie(message, workspace):
    """
    Call Augment CLI (auggie) to get AI response using PTY.

    Uses a pseudo-terminal to properly interact with auggie's interactive mode.
    """
    import signal

    try:
        # Ensure workspace exists
        if not os.path.isdir(workspace):
            workspace = os.path.expanduser('~')

        # Create a pseudo-terminal
        master_fd, slave_fd = pty.openpty()

        # Set up environment
        env = os.environ.copy()
        env['TERM'] = 'xterm-256color'
        env['AUGMENT_WORKSPACE'] = workspace
        env['COLUMNS'] = '200'
        env['LINES'] = '100'

        # Start auggie process with PTY
        process = subprocess.Popen(
            ['auggie'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=workspace,
            env=env,
            preexec_fn=os.setsid
        )

        os.close(slave_fd)

        # Wait for auggie to start and show the input prompt
        start_time = time.time()
        initial_output = ""
        prompt_ready = False

        while time.time() - start_time < 15:
            ready, _, _ = select.select([master_fd], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                    initial_output += chunk
                    # Check for the input box prompt (› character in input box)
                    if '›' in chunk:
                        prompt_ready = True
                        # Brief wait for UI to stabilize
                        time.sleep(0.5)
                        # Drain any remaining initial output
                        while True:
                            ready2, _, _ = select.select([master_fd], [], [], 0.2)
                            if ready2:
                                try:
                                    extra = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                                    initial_output += extra
                                except:
                                    break
                            else:
                                break
                        break
                except OSError:
                    break

        if not prompt_ready:
            raise Exception("Auggie didn't start properly - no prompt detected")

        # Reset start_time for response timeout tracking
        response_start_time = time.time()

        # Send the user's message followed by Enter (CR+LF to submit)
        os.write(master_fd, message.encode('utf-8'))
        time.sleep(0.1)
        os.write(master_fd, b'\r')  # Carriage return
        time.sleep(0.1)
        os.write(master_fd, b'\n')  # Line feed to submit

        # Read the response - wait for AI to think and respond
        # Start with initial_output so we can track what's new
        all_output = initial_output
        initial_length = len(strip_ansi(initial_output))  # Track where initial output ends

        last_data_time = time.time()
        message_sent_time = time.time()
        saw_message_echo = False
        saw_response_marker = False  # The ● marker indicates actual AI response
        response_complete = False
        timeout = 300  # 5 minutes max

        # Wait for the response - use a simpler approach:
        # 1. Read until we stop getting data for a while
        # 2. After message echo, wait for substantial content + no new data

        while time.time() - response_start_time < timeout:
            ready, _, _ = select.select([master_fd], [], [], 0.3)  # Faster polling
            if ready:
                try:
                    chunk = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        all_output += chunk
                        last_data_time = time.time()

                        # Get the clean version of ALL output
                        clean_all = strip_ansi(all_output)
                        # Only look at NEW content (after initial output)
                        new_content = clean_all[initial_length:]

                        # Check if our message appears in the NEW content (echoed back)
                        if message in new_content:
                            if not saw_message_echo:
                                saw_message_echo = True

                        # After seeing echo, look for response marker AFTER our message
                        if saw_message_echo:
                            msg_pos = new_content.find(message)
                            if msg_pos >= 0:
                                after_message = new_content[msg_pos + len(message):]

                                # Look for ● marker that comes AFTER the spinner
                                if '●' in after_message:
                                    bullet_pos = after_message.find('●')
                                    after_bullet = after_message[bullet_pos:]
                                    if 'Sending request' not in after_bullet[:50]:
                                        if not saw_response_marker:
                                            saw_response_marker = True

                                        # KEY OPTIMIZATION: Check if new prompt appeared
                                        # The prompt box pattern indicates response is complete
                                        # Look for the input prompt pattern after the response
                                        if re.search(r'│ ›\s*│', after_bullet) or re.search(r'╰─+╯', after_bullet[-200:]):
                                            response_complete = True
                                            # Small delay to ensure we got everything
                                            time.sleep(0.3)
                                            # Drain any remaining data
                                            while True:
                                                r, _, _ = select.select([master_fd], [], [], 0.2)
                                                if r:
                                                    try:
                                                        extra = os.read(master_fd, 8192).decode('utf-8', errors='ignore')
                                                        all_output += extra
                                                    except:
                                                        pass
                                                else:
                                                    break
                                            break
                except OSError:
                    break
            else:
                # No new data for this interval
                elapsed_no_data = time.time() - last_data_time
                elapsed_since_send = time.time() - message_sent_time

                # If we saw the response marker and no new data for 2+ seconds, we're done
                if saw_response_marker and elapsed_no_data > 2:
                    response_complete = True
                    break

                # If we saw the echo but not response marker, and it's been a while
                if saw_message_echo and not saw_response_marker and elapsed_since_send > 60:
                    break

                # Absolute timeout
                if elapsed_since_send > 180 and elapsed_no_data > 10:
                    break

        # Get just the new content (after initial output) for response extraction
        new_content = strip_ansi(all_output)[initial_length:]

        # Clean up the process
        try:
            os.kill(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except:
                pass

        try:
            os.close(master_fd)
        except:
            pass

        # Extract the response from the new content
        # The content should contain:
        # - Our echoed message
        # - ~ Thinking (optional)
        # - ● The response
        # - New prompt box

        # Normalize line endings
        new_content = new_content.replace('\r\n', '\n').replace('\r', '\n')

        # Find content after our message
        if message in new_content:
            msg_pos = new_content.find(message)
            after_message = new_content[msg_pos + len(message):]

            # Find the last ● marker (the actual response, not from initial output)
            # and extract everything until the prompt box appears
            last_bullet = after_message.rfind('●')
            if last_bullet >= 0:
                response_section = after_message[last_bullet + 1:]

                # Find where the prompt box starts (╭─── or │ › pattern)
                # This marks the end of the response
                prompt_patterns = [
                    r'\n\s*╭─+',  # Start of prompt box
                    r'\n\s*│\s*›',  # Input prompt line
                    r'\n\s*╰─+',  # End of prompt box
                ]

                end_pos = len(response_section)
                for pattern in prompt_patterns:
                    match = re.search(pattern, response_section)
                    if match and match.start() < end_pos:
                        end_pos = match.start()

                response_text = response_section[:end_pos].strip()

                # Clean up box drawing characters and UI elements
                response_text = re.sub(r'[╭╮╯╰│─╗╔║╚╝═]+', '', response_text)
                response_text = re.sub(r'\[Claude.*?\].*', '', response_text)
                response_text = re.sub(r'\? to show shortcuts.*', '', response_text)
                response_text = re.sub(r'Ctrl\+[A-Z].*', '', response_text)
                response_text = re.sub(r'\n{3,}', '\n\n', response_text)
                # Clean up extra whitespace at start of lines (from TUI formatting)
                response_text = re.sub(r'\n\s{3,}', '\n', response_text)
                response_text = response_text.strip()

                if response_text:
                    return response_text

        # Fallback: Try finding ● in full new_content
        last_bullet = new_content.rfind('●')
        if last_bullet >= 0:
            response_section = new_content[last_bullet + 1:]

            # Find where the prompt box starts
            end_pos = len(response_section)
            for pattern in [r'\n\s*╭─+', r'\n\s*│\s*›', r'\n\s*╰─+']:
                match = re.search(pattern, response_section)
                if match and match.start() < end_pos:
                    end_pos = match.start()

            response_text = response_section[:end_pos].strip()
            response_text = re.sub(r'[╭╮╯╰│─╗╔║╚╝═]+', '', response_text)
            response_text = re.sub(r'\n{3,}', '\n\n', response_text)
            response_text = re.sub(r'\n\s{3,}', '\n', response_text)
            response_text = response_text.strip()

            if response_text and len(response_text) > 0:
                return response_text

        # Fallback: return a message indicating we didn't parse it correctly
        return f"Auggie processed your request but response parsing failed.\n\nRaw new content (last 500 chars): {new_content[-500:]}"

    except Exception as e:
        raise Exception(f"Error communicating with Auggie: {str(e)}")


@app.route('/api/check-auth')
def check_auth():
    """Check if user is authenticated with Augment"""
    try:
        result = subprocess.run(
            ['npx', '@augmentcode/auggie', '--help'],
            capture_output=True,
            text=True,
            timeout=30
        )
        return jsonify({
            'authenticated': True,
            'status': 'ready',
            'workspace': settings['workspace']
        })
    except Exception as e:
        return jsonify({'authenticated': False, 'error': str(e)})


@app.route('/api/browse', methods=['GET'])
def browse_directories():
    """Browse directories for workspace selection"""
    path = request.args.get('path', os.path.expanduser('~'))
    path = os.path.expanduser(path)

    try:
        if not os.path.isdir(path):
            path = os.path.expanduser('~')

        items = []
        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                items.append({
                    'name': item,
                    'path': item_path,
                    'type': 'directory'
                })

        return jsonify({
            'current': path,
            'parent': os.path.dirname(path),
            'items': items[:50]  # Limit to 50 items
        })
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🤖 AI Chat Application (Powered by Augment Code)")
    print("=" * 60)
    print(f"📁 Default workspace: {settings['workspace']}")
    print("💡 You can change the workspace in the app settings")
    print("")
    print("🌐 Open your browser: http://localhost:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000, threaded=True)

