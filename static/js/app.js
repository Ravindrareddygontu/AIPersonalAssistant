// Chat Application JavaScript - Powered by Augment Code

let chatHistory = [];
let currentChatId = null;
let isProcessing = false;
let currentWorkspace = '~';
let browserCurrentPath = '';
let sidebarOpen = true;

// Initialize the app
document.addEventListener('DOMContentLoaded', async () => {
    loadSettings();
    checkAuthStatus();
    loadWorkspaceFromServer();

    // Restore sidebar state
    const savedSidebarState = localStorage.getItem('sidebarOpen');
    if (savedSidebarState === 'false') {
        toggleSidebar();
    }

    // Load chats and restore last active chat
    await loadChatsFromServer();

    // Try to restore the last active chat
    const savedChatId = localStorage.getItem('currentChatId');
    if (savedChatId) {
        await loadChatFromServer(savedChatId);
    }
});

// Load workspace from server
async function loadWorkspaceFromServer() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        if (data.workspace) {
            currentWorkspace = data.workspace;
            updateWorkspaceDisplay();
        }
    } catch (error) {
        console.error('Failed to load workspace:', error);
    }
}

// Update workspace display
function updateWorkspaceDisplay() {
    const display = document.getElementById('workspaceDisplay');
    const input = document.getElementById('workspaceInput');
    const current = document.getElementById('currentWorkspace');

    // Shorten path for display
    let shortPath = currentWorkspace;
    if (shortPath.startsWith('/home/')) {
        shortPath = '~' + shortPath.substring(shortPath.indexOf('/', 6));
    }
    if (shortPath.length > 30) {
        shortPath = '...' + shortPath.substring(shortPath.length - 27);
    }

    if (display) display.textContent = shortPath;
    if (input) input.value = currentWorkspace;
    if (current) current.innerHTML = `<i class="fas fa-folder-open"></i> Current: ${currentWorkspace}`;
}

// Check Augment authentication status
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/check-auth');
        const data = await response.json();
        const statusEl = document.getElementById('authStatus');
        if (statusEl) {
            if (data.authenticated) {
                statusEl.innerHTML = `
                    <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
                    <span>Connected via Augment Code</span>
                `;
                if (data.workspace) {
                    currentWorkspace = data.workspace;
                    updateWorkspaceDisplay();
                }
            } else {
                statusEl.innerHTML = `
                    <i class="fas fa-exclamation-circle" style="color: var(--error-color);"></i>
                    <span>Not connected - run 'npx @augmentcode/auggie --login'</span>
                `;
            }
        }
    } catch (error) {
        console.error('Auth check failed:', error);
    }
}

// Send message function with streaming status updates
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    console.log('sendMessage called, message:', message);

    if (!message || isProcessing) {
        console.log('Skipping - empty message or processing');
        return;
    }

    // Clear input and hide welcome
    input.value = '';
    autoResize(input);
    hideWelcome();

    // Add user message
    addMessage('user', message);
    console.log('User message added');

    // Show typing indicator with initial status
    showTypingIndicator('Connecting...');
    isProcessing = true;
    document.getElementById('sendBtn').disabled = true;

    try {
        console.log('Sending to streaming API...');
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                workspace: currentWorkspace
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamingCompleted = false;  // Track if streaming was used

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        console.log('SSE event:', data);

                        if (data.type === 'status') {
                            updateTypingStatus(data.message);
                        } else if (data.type === 'stream_start') {
                            // Start streaming - create message container
                            hideTypingIndicator();
                            startStreamingMessage();
                        } else if (data.type === 'stream') {
                            // Append streaming content
                            appendStreamingContent(data.content);
                        } else if (data.type === 'stream_end') {
                            // Finalize streaming with complete formatted content
                            finalizeStreamingMessage(data.content);
                            hideTypingIndicator();  // Remove status box
                            streamingCompleted = true;
                            console.log('Streaming complete');
                        } else if (data.type === 'response') {
                            // Only add message if streaming wasn't used
                            if (!streamingCompleted) {
                                hideTypingIndicator();
                                addMessage('assistant', data.message);
                                console.log('Assistant message added (non-streaming)');
                            }
                            if (data.workspace && data.workspace !== currentWorkspace) {
                                currentWorkspace = data.workspace;
                                updateWorkspaceDisplay();
                            }
                        } else if (data.type === 'error') {
                            hideTypingIndicator();
                            addMessage('assistant', `❌ Error: ${data.message}`);
                        }
                    } catch (e) {
                        console.log('Parse error:', e, 'Line:', line);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        hideTypingIndicator();
        addMessage('assistant', '❌ Sorry, there was an error connecting to the server. Make sure the server is running and try again.');
    }

    isProcessing = false;
    document.getElementById('sendBtn').disabled = false;
}

// Add message to chat
function addMessage(role, content) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    const messageIndex = chatHistory.length; // Index before adding

    const icon = role === 'user' ? 'fa-user' : 'fa-robot';

    // User messages get edit button, assistant messages get copy button
    const actionBtn = role === 'assistant' ? `
        <div class="message-actions">
            <button class="copy-btn" onclick="copyMessage(this, '${encodeURIComponent(content)}')">
                <i class="fas fa-copy"></i> Copy
            </button>
        </div>
    ` : `
        <div class="message-actions user-actions">
            <button class="edit-btn" onclick="editMessage(this, ${messageIndex}, '${encodeURIComponent(content)}')">
                <i class="fas fa-edit"></i> Edit
            </button>
        </div>
    `;

    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas ${icon}"></i>
        </div>
        <div class="message-content">
            ${actionBtn}
            <div class="message-text">${formatMessage(content)}</div>
        </div>
    `;

    container.appendChild(messageDiv);

    // Add copy buttons to code blocks
    addCodeCopyButtons(messageDiv);

    // Add to history
    chatHistory.push({ role, content });
    saveCurrentChatToServer();

    // Scroll to bottom after DOM update
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 50);
}

// Streaming message state
let streamingMessageDiv = null;
let streamingContent = '';
let streamingUpdatePending = false;
let lastStreamingUpdate = 0;

// Start a new streaming message
function startStreamingMessage() {
    const container = document.getElementById('chatMessages');

    // Create the message container
    streamingMessageDiv = document.createElement('div');
    streamingMessageDiv.className = 'message assistant streaming';
    streamingMessageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text streaming-text"></div>
            <div class="streaming-cursor"></div>
        </div>
    `;

    container.appendChild(streamingMessageDiv);
    streamingContent = '';
    streamingUpdatePending = false;
    lastStreamingUpdate = 0;

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Append content to streaming message with batched updates for performance
function appendStreamingContent(newContent) {
    if (!streamingMessageDiv) return;

    streamingContent += newContent;

    // Batch updates: only update DOM every 30ms or when we have significant content
    const now = Date.now();
    const timeSinceLastUpdate = now - lastStreamingUpdate;

    // Update immediately if it's been a while, or batch small updates
    if (timeSinceLastUpdate > 30 || newContent.includes('\n') || streamingContent.length < 50) {
        updateStreamingDisplay();
        lastStreamingUpdate = now;
    } else if (!streamingUpdatePending) {
        // Schedule an update
        streamingUpdatePending = true;
        requestAnimationFrame(() => {
            updateStreamingDisplay();
            streamingUpdatePending = false;
            lastStreamingUpdate = Date.now();
        });
    }
}

// Actually update the streaming display
function updateStreamingDisplay() {
    if (!streamingMessageDiv) return;

    const textDiv = streamingMessageDiv.querySelector('.streaming-text');
    if (textDiv) {
        // Format and display the content
        textDiv.innerHTML = formatMessage(streamingContent);
    }

    // Scroll to bottom
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

// Finalize streaming message with complete formatted content
function finalizeStreamingMessage(finalContent) {
    if (!streamingMessageDiv) return;

    const container = document.getElementById('chatMessages');

    // Remove streaming class and cursor
    streamingMessageDiv.classList.remove('streaming');
    const cursor = streamingMessageDiv.querySelector('.streaming-cursor');
    if (cursor) cursor.remove();

    // Get the text div and current streamed content
    const textDiv = streamingMessageDiv.querySelector('.streaming-text');

    // Use finalContent if provided, otherwise keep the streamed content
    const contentToUse = finalContent && finalContent.trim() ? finalContent : (streamingContent || '');

    textDiv.className = 'message-text';
    textDiv.innerHTML = formatMessage(contentToUse);

    // Add action buttons
    const contentDiv = streamingMessageDiv.querySelector('.message-content');
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';
    actionsDiv.innerHTML = `
        <button class="copy-btn" onclick="copyMessage(this, '${encodeURIComponent(contentToUse)}')">
            <i class="fas fa-copy"></i> Copy
        </button>
    `;
    contentDiv.insertBefore(actionsDiv, contentDiv.firstChild);

    // Add copy buttons to code blocks
    addCodeCopyButtons(streamingMessageDiv);

    // Add to history
    chatHistory.push({ role: 'assistant', content: contentToUse });
    saveCurrentChatToServer();

    // Reset streaming state
    streamingMessageDiv = null;
    streamingContent = '';

    // Final scroll
    container.scrollTop = container.scrollHeight;
}

// Edit and resubmit a user message
function editMessage(btn, messageIndex, encodedContent) {
    if (isProcessing) {
        return; // Don't allow editing while processing
    }

    const content = decodeURIComponent(encodedContent);
    const container = document.getElementById('chatMessages');
    const messages = container.querySelectorAll('.message');

    // Find the message element
    const userMessageEl = btn.closest('.message');
    const userMessageIdx = Array.from(messages).indexOf(userMessageEl);

    // Remove this message and all messages after it (including the answer)
    const messagesToRemove = [];
    for (let i = messages.length - 1; i >= userMessageIdx; i--) {
        messagesToRemove.push(messages[i]);
    }
    messagesToRemove.forEach(el => el.remove());

    // Also remove any status logs that might be orphaned
    const statusLogs = container.querySelectorAll('.status-log');
    statusLogs.forEach(log => {
        // Check if this status log is after the removed messages
        const allElements = Array.from(container.children);
        const logIdx = allElements.indexOf(log);
        if (logIdx >= userMessageIdx) {
            log.remove();
        }
    });

    // Update chat history - remove from the messageIndex onwards
    chatHistory = chatHistory.slice(0, messageIndex);
    saveCurrentChatToServer();

    // Put the content back in the input
    const input = document.getElementById('messageInput');
    input.value = content;
    autoResize(input);
    input.focus();

    // Show welcome message if no messages left
    if (chatHistory.length === 0) {
        const welcomeEl = document.getElementById('welcomeMessage');
        if (welcomeEl) {
            welcomeEl.style.display = 'block';
        }
    }
}

// Copy message content
function copyMessage(btn, encodedContent) {
    const content = decodeURIComponent(encodedContent);
    navigator.clipboard.writeText(content).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
            btn.classList.remove('copied');
        }, 2000);
    });
}

// Add copy buttons to code blocks
function addCodeCopyButtons(container) {
    const codeBlocks = container.querySelectorAll('pre');
    codeBlocks.forEach(pre => {
        const code = pre.querySelector('code');
        if (code) {
            const btn = document.createElement('button');
            btn.className = 'copy-code-btn';
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
            btn.onclick = () => {
                navigator.clipboard.writeText(code.textContent).then(() => {
                    btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                        btn.classList.remove('copied');
                    }, 2000);
                });
            };
            pre.appendChild(btn);
        }
    });
}

// Format message with code blocks and markdown
function formatMessage(text) {
    // Normalize line endings (handle \r\n and \r)
    text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // Escape HTML first (but we'll handle special cases)
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // Code blocks - extract and protect them first
    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${code}</code></pre>`);
        return `__CODE_BLOCK_${index}__`;
    });

    // Inline code - protect these too
    const inlineCodes = [];
    text = text.replace(/`([^`]+)`/g, (match, code) => {
        const index = inlineCodes.length;
        inlineCodes.push(`<code>${code}</code>`);
        return `__INLINE_CODE_${index}__`;
    });

    // Tables - detect and convert markdown tables
    text = text.replace(/^(\|.+\|)\n(\|[-:\s|]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, separator, body) => {
        const headerCells = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
        const bodyRows = body.trim().split('\n').map(row => {
            const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<table class="md-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table>`;
    });

    // Headers
    text = text.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic (but not if it's part of a bullet point indicator)
    text = text.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // Bullet points - convert to proper list
    const lines = text.split('\n');
    let inList = false;
    let listType = null;
    const processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const bulletMatch = line.match(/^[\s]*[•\-\*]\s+(.+)$/);
        const numberedMatch = line.match(/^[\s]*(\d+)\.\s+(.+)$/);
        const subItemMatch = line.match(/^[\s]*(↳|⎿)\s+(.+)$/);

        if (bulletMatch) {
            if (!inList || listType !== 'ul') {
                if (inList) processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
                processedLines.push('<ul class="md-list">');
                inList = true;
                listType = 'ul';
            }
            processedLines.push(`<li>${bulletMatch[1]}</li>`);
        } else if (numberedMatch) {
            if (!inList || listType !== 'ol') {
                if (inList) processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
                processedLines.push('<ol class="md-list">');
                inList = true;
                listType = 'ol';
            }
            processedLines.push(`<li>${numberedMatch[2]}</li>`);
        } else if (subItemMatch) {
            // Sub-items (↳ or ⎿)
            processedLines.push(`<div class="sub-item"><span class="sub-arrow">↳</span> ${subItemMatch[2]}</div>`);
        } else {
            if (inList) {
                processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
                inList = false;
                listType = null;
            }
            processedLines.push(line);
        }
    }
    if (inList) {
        processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
    }
    text = processedLines.join('\n');

    // Line breaks - but not inside HTML tags
    // Double newlines become paragraph breaks
    text = text.replace(/\n\n+/g, '</p><p>');
    // Single newlines become <br> (but not after block elements)
    text = text.replace(/(?<!<\/(?:h[1-6]|p|ul|ol|li|table|thead|tbody|tr|th|td|pre|div)>)\n(?!<)/g, '<br>');

    // Wrap in paragraph
    text = '<p>' + text + '</p>';

    // Clean up empty paragraphs
    text = text.replace(/<p>\s*<\/p>/g, '');
    text = text.replace(/<p>\s*<(ul|ol|table|h[1-6]|pre)/g, '<$1');
    text = text.replace(/<\/(ul|ol|table|h[1-6]|pre)>\s*<\/p>/g, '</$1>');

    // Restore code blocks
    codeBlocks.forEach((block, index) => {
        text = text.replace(`__CODE_BLOCK_${index}__`, block);
    });

    // Restore inline code
    inlineCodes.forEach((code, index) => {
        text = text.replace(`__INLINE_CODE_${index}__`, code);
    });

    return text;
}

// Generic status messages that should be overwritten (not stacked)
const genericStatuses = [
    'Connecting...', 'Starting Augment...', 'Waiting for Augment to initialize...',
    'Sending your message...', 'Waiting for AI response...', 'Processing your request...',
    'AI is thinking...', 'Receiving response...', 'Finalizing response...'
];

// Show/hide typing indicator with status message
function showTypingIndicator(statusMessage = 'Thinking...') {
    const container = document.getElementById('chatMessages');

    // Remove any existing status log from previous question (prevent duplicate IDs)
    const existingStatusLog = document.getElementById('statusLog');
    if (existingStatusLog && !existingStatusLog.classList.contains('complete')) {
        existingStatusLog.remove();
    }

    // Remove any existing typing indicator
    const existingTyping = document.getElementById('typingIndicator');
    if (existingTyping) {
        existingTyping.remove();
    }

    // Create status log container with unique ID
    const uniqueId = Date.now();
    const statusLogDiv = document.createElement('div');
    statusLogDiv.className = 'status-log';
    statusLogDiv.id = 'statusLog';
    statusLogDiv.setAttribute('data-id', uniqueId);
    statusLogDiv.innerHTML = `
        <div class="status-generic" id="statusGeneric">
            <i class="fas fa-circle-notch fa-spin"></i> <span id="genericStatusText">${statusMessage}</span>
        </div>
        <div class="status-details" id="statusDetails"></div>
    `;
    container.appendChild(statusLogDiv);

    // Create typing indicator (just dots)
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    container.appendChild(typingDiv);
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 50);
}

// Get the current (non-complete) status log
function getCurrentStatusLog() {
    // Get all status logs and find the one that's NOT complete
    const allStatusLogs = document.querySelectorAll('.status-log:not(.complete)');
    if (allStatusLogs.length > 0) {
        return allStatusLogs[allStatusLogs.length - 1]; // Return the last non-complete one
    }
    return null;
}

// Update typing status message
function updateTypingStatus(message) {
    const statusLog = getCurrentStatusLog();
    if (!statusLog) return;

    // Check if it's a generic status (overwrite) or detailed status (stack)
    const isGeneric = genericStatuses.some(g => message.includes(g) || g.includes(message));

    if (isGeneric) {
        // Overwrite the generic status line
        const genericText = statusLog.querySelector('#genericStatusText');
        if (genericText) {
            genericText.textContent = message;
        }
    } else {
        // Add to detailed status list (these are the action messages)
        const statusDetails = statusLog.querySelector('#statusDetails');
        if (statusDetails) {
            const statusItem = document.createElement('div');
            statusItem.className = 'status-item';
            // Check if it's a sub-action (starts with ↳ or spaces)
            if (message.trim().startsWith('↳') || message.trim().startsWith('⎿')) {
                statusItem.className = 'status-item sub-action';
                statusItem.innerHTML = `<i class="fas fa-check"></i> ${message.trim()}`;
            } else {
                statusItem.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> ${message}`;
            }
            statusDetails.appendChild(statusItem);
        }
    }

    const container = document.getElementById('chatMessages');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 50);
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();

    // Remove the status log completely
    const statusLog = getCurrentStatusLog();
    if (statusLog) {
        statusLog.remove();
    }

    // Also remove any status logs marked as complete
    const completeLogs = document.querySelectorAll('.status-log.complete');
    completeLogs.forEach(log => log.remove());
}

// Hide welcome message
function hideWelcome() {
    const welcome = document.querySelector('.welcome-message');
    if (welcome) welcome.style.display = 'none';
}

// Send suggestion
function sendSuggestion(text) {
    document.getElementById('messageInput').value = text;
    sendMessage();
}

// Handle keyboard input
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Auto-resize textarea
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

// New chat (legacy - calls createNewChat)
function newChat() {
    createNewChat();
}

// Refresh page
function refreshPage() {
    location.reload();
}

// Toggle settings modal
function toggleSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.toggle('active');
}

// Toggle theme
function toggleTheme() {
    const isLight = document.body.classList.contains('light-theme');
    applyTheme(isLight ? 'dark' : 'light');
}

// Apply theme
function applyTheme(theme) {
    const icon = document.querySelector('#themeToggle i');
    if (theme === 'light') {
        document.body.classList.add('light-theme');
        if (icon) {
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
        }
    } else {
        document.body.classList.remove('light-theme');
        if (icon) {
            icon.classList.remove('fa-sun');
            icon.classList.add('fa-moon');
        }
    }
    localStorage.setItem('theme', theme);
}

// Load settings
function loadSettings() {
    const theme = localStorage.getItem('theme');
    const themeSelect = document.getElementById('themeSelect');
    const savedWorkspace = localStorage.getItem('workspace');

    if (theme) {
        applyTheme(theme);
        if (themeSelect) themeSelect.value = theme;
    }

    if (savedWorkspace) {
        currentWorkspace = savedWorkspace;
        updateWorkspaceDisplay();
    }
}

// Save workspace
async function saveWorkspace() {
    const input = document.getElementById('workspaceInput');
    const workspace = input.value.trim() || currentWorkspace;

    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace })
        });

        const data = await response.json();
        if (data.status === 'success') {
            currentWorkspace = data.workspace || workspace;
            localStorage.setItem('workspace', currentWorkspace);
            updateWorkspaceDisplay();
            showNotification('Workspace saved!');
            toggleSettings();
        } else {
            showNotification('Error: ' + (data.error || 'Failed to save'));
        }
    } catch (error) {
        showNotification('Error saving workspace');
    }
}

// Browse workspace directories
async function browseWorkspace() {
    browserCurrentPath = currentWorkspace || '~';
    await loadBrowserDirectory(browserCurrentPath);
    document.getElementById('browserModal').classList.add('active');
}

// Load directory contents
async function loadBrowserDirectory(path) {
    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (data.error) {
            showNotification('Error: ' + data.error);
            return;
        }

        browserCurrentPath = data.current;
        document.getElementById('browserPath').textContent = data.current;

        const list = document.getElementById('browserList');
        list.innerHTML = '';

        // Add parent directory option
        if (data.parent && data.parent !== data.current) {
            const parentItem = document.createElement('div');
            parentItem.className = 'browser-item parent';
            parentItem.innerHTML = '<i class="fas fa-level-up-alt"></i> <span>.. (Parent Directory)</span>';
            parentItem.onclick = () => loadBrowserDirectory(data.parent);
            list.appendChild(parentItem);
        }

        // Add directories
        data.items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'browser-item';
            div.innerHTML = `<i class="fas fa-folder"></i> <span>${item.name}</span>`;
            div.onclick = () => loadBrowserDirectory(item.path);
            list.appendChild(div);
        });

        if (data.items.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'browser-item';
            empty.innerHTML = '<i class="fas fa-info-circle"></i> <span>No subdirectories</span>';
            list.appendChild(empty);
        }

    } catch (error) {
        showNotification('Error loading directory');
    }
}

// Select current directory from browser
function selectCurrentDir() {
    document.getElementById('workspaceInput').value = browserCurrentPath;
    closeBrowser();
}

// Close browser modal
function closeBrowser() {
    document.getElementById('browserModal').classList.remove('active');
}

// Toggle sidebar
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebarOpen = !sidebarOpen;
    sidebar.classList.toggle('collapsed', !sidebarOpen);
    localStorage.setItem('sidebarOpen', sidebarOpen);
}

// Load chats from server
async function loadChatsFromServer() {
    try {
        const response = await fetch('/api/chats');
        const chats = await response.json();
        renderChatHistory(chats);
    } catch (error) {
        console.error('Failed to load chats:', error);
    }
}

// Render chat history in sidebar
function renderChatHistory(chats) {
    const container = document.getElementById('chatHistory');
    if (!container) return;

    container.innerHTML = '';

    if (chats.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.85rem;">
                <i class="fas fa-comments" style="font-size: 2rem; margin-bottom: 10px; display: block;"></i>
                No chat history yet
            </div>
        `;
        return;
    }

    chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = `chat-history-item ${chat.id === currentChatId ? 'active' : ''}`;
        item.onclick = (e) => {
            if (!e.target.closest('.delete-chat-btn')) {
                loadChatFromServer(chat.id);
            }
        };

        // Format date
        const date = new Date(chat.updated_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        item.innerHTML = `
            <i class="fas fa-message"></i>
            <span class="chat-title">${escapeHtml(chat.title)}</span>
            <button class="delete-chat-btn" onclick="deleteChat('${chat.id}', event)" title="Delete chat">
                <i class="fas fa-trash"></i>
            </button>
        `;
        container.appendChild(item);
    });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Create new chat
async function createNewChat() {
    try {
        // Reset the auggie session to start fresh context
        await fetch('/api/session/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace: currentWorkspace })
        });

        const response = await fetch('/api/chats', { method: 'POST' });
        const chat = await response.json();

        currentChatId = chat.id;
        chatHistory = [];
        localStorage.setItem('currentChatId', currentChatId);

        // Reset the chat UI
        const container = document.getElementById('chatMessages');
        container.innerHTML = `
            <div class="welcome-message">
                <h2>What can I help you with?</h2>
                <div class="quick-actions">
                    <button class="action-btn" onclick="sendSuggestion('Show me the structure of this project')">
                        <i class="fas fa-sitemap"></i>
                        Project structure
                    </button>
                    <button class="action-btn" onclick="sendSuggestion('List all files in the current directory')">
                        <i class="fas fa-folder-tree"></i>
                        List files
                    </button>
                    <button class="action-btn" onclick="sendSuggestion('Help me fix a bug in my code')">
                        <i class="fas fa-bug"></i>
                        Fix bug
                    </button>
                    <button class="action-btn" onclick="sendSuggestion('Write a function that')">
                        <i class="fas fa-code"></i>
                        Write code
                    </button>
                    <button class="action-btn" onclick="sendSuggestion('Explain this code:')">
                        <i class="fas fa-book-open"></i>
                        Explain code
                    </button>
                    <button class="action-btn" onclick="sendSuggestion('Run the tests')">
                        <i class="fas fa-flask"></i>
                        Run tests
                    </button>
                </div>
            </div>
        `;

        // Refresh the chat history sidebar
        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to create chat:', error);
        showNotification('Failed to create new chat');
    }
}

// Save current chat to server
async function saveCurrentChatToServer() {
    if (!currentChatId || chatHistory.length === 0) return;

    try {
        await fetch(`/api/chats/${currentChatId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatHistory })
        });

        // Refresh the sidebar to show updated title
        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to save chat:', error);
    }
}

// Load chat from server
async function loadChatFromServer(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        const chat = await response.json();

        if (chat.error) {
            showNotification('Chat not found');
            return;
        }

        currentChatId = chatId;
        chatHistory = chat.messages || [];
        localStorage.setItem('currentChatId', currentChatId);

        const container = document.getElementById('chatMessages');
        container.innerHTML = '';

        if (chatHistory.length === 0) {
            container.innerHTML = `
                <div class="welcome-message">
                    <h2>What can I help you with?</h2>
                    <div class="quick-actions">
                        <button class="action-btn" onclick="sendSuggestion('Show me the structure of this project')">
                            <i class="fas fa-sitemap"></i>
                            Project structure
                        </button>
                        <button class="action-btn" onclick="sendSuggestion('List all files in the current directory')">
                            <i class="fas fa-folder-tree"></i>
                            List files
                        </button>
                        <button class="action-btn" onclick="sendSuggestion('Help me fix a bug in my code')">
                            <i class="fas fa-bug"></i>
                            Fix bug
                        </button>
                        <button class="action-btn" onclick="sendSuggestion('Write a function that')">
                            <i class="fas fa-code"></i>
                            Write code
                        </button>
                    </div>
                </div>
            `;
        } else {
            chatHistory.forEach((msg, idx) => {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${msg.role}`;
                const icon = msg.role === 'user' ? 'fa-user' : 'fa-robot';

                // User messages get edit button, assistant messages get copy button
                const actionBtn = msg.role === 'assistant' ? `
                    <div class="message-actions">
                        <button class="copy-btn" onclick="copyMessage(this, '${encodeURIComponent(msg.content)}')">
                            <i class="fas fa-copy"></i> Copy
                        </button>
                    </div>
                ` : `
                    <div class="message-actions user-actions">
                        <button class="edit-btn" onclick="editMessage(this, ${idx}, '${encodeURIComponent(msg.content)}')">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                    </div>
                `;

                messageDiv.innerHTML = `
                    <div class="message-avatar">
                        <i class="fas ${icon}"></i>
                    </div>
                    <div class="message-content">
                        ${actionBtn}
                        <div class="message-text">${formatMessage(msg.content)}</div>
                    </div>
                `;
                container.appendChild(messageDiv);
                addCodeCopyButtons(messageDiv);
            });
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 50);
        }

        // Update sidebar selection
        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to load chat:', error);
        showNotification('Failed to load chat');
    }
}

// Delete a chat
async function deleteChat(chatId, event) {
    if (event) event.stopPropagation();

    if (!confirm('Delete this chat?')) return;

    try {
        await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });

        // If we deleted the current chat, create a new one
        if (chatId === currentChatId) {
            createNewChat();
        } else {
            loadChatsFromServer();
        }

        showNotification('Chat deleted');
    } catch (error) {
        console.error('Failed to delete chat:', error);
        showNotification('Failed to delete chat');
    }
}

// Clear all chats
async function clearAllChats() {
    if (!confirm('Delete all chat history? This cannot be undone.')) return;

    try {
        await fetch('/api/chats/clear', { method: 'DELETE' });
        createNewChat();
        showNotification('All chats cleared');
    } catch (error) {
        console.error('Failed to clear chats:', error);
        showNotification('Failed to clear chats');
    }
}

// Legacy function - kept for compatibility
function loadChatHistory() {
    loadChatsFromServer();
}

// Show notification
function showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--primary-color);
        color: white;
        padding: 12px 24px;
        border-radius: 10px;
        z-index: 1001;
        animation: fadeIn 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => notification.remove(), 3000);
}

