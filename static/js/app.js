// Chat Application JavaScript - Powered by Augment Code

let chatHistory = [];
let currentChatId = null;
let isProcessing = false;
let currentWorkspace = '~';
let browserCurrentPath = '';
let sidebarOpen = true;
let currentAbortController = null;

// Generate a unique message ID based on chatId, index, and content hash
function generateMessageId(chatId, index, content) {
    // Create a simple hash of the content
    let hash = 0;
    const str = content.substring(0, 100); // Use first 100 chars for hash
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    return `${chatId}-${index}-${Math.abs(hash).toString(16)}`;
}

// Shared welcome message HTML
const WELCOME_HTML = `
    <div class="welcome-message">
        <h2>What can I help you with?</h2>
        <div class="quick-actions">
            <button class="action-btn" onclick="sendSuggestion('Show me the structure of this project')">
                <i class="fas fa-sitemap"></i> Project structure
            </button>
            <button class="action-btn" onclick="sendSuggestion('List all files in the current directory')">
                <i class="fas fa-folder-tree"></i> List files
            </button>
            <button class="action-btn" onclick="sendSuggestion('Help me fix a bug in my code')">
                <i class="fas fa-bug"></i> Fix bug
            </button>
            <button class="action-btn" onclick="sendSuggestion('Write a function that')">
                <i class="fas fa-code"></i> Write code
            </button>
            <button class="action-btn" onclick="sendSuggestion('Explain this code:')">
                <i class="fas fa-book-open"></i> Explain code
            </button>
            <button class="action-btn" onclick="sendSuggestion('Run the tests')">
                <i class="fas fa-flask"></i> Run tests
            </button>
        </div>
    </div>
`;

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

// Save chat before page unload (refresh/close)
window.addEventListener('beforeunload', (event) => {
    console.log('[UNLOAD] beforeunload triggered, streamingMessageDiv:', !!streamingMessageDiv);
    // If there's an active streaming message, finalize it before leaving
    if (streamingMessageDiv && streamingContent) {
        console.log('[UNLOAD] Finalizing streaming message before unload');
        // Synchronously add to history (can't use async here)
        chatHistory.push({ role: 'assistant', content: streamingContent });
        // Use sendBeacon for reliable save on unload
        if (currentChatId && navigator.sendBeacon) {
            const data = JSON.stringify({ messages: chatHistory });
            navigator.sendBeacon(`/api/chats/${currentChatId}`, new Blob([data], { type: 'application/json' }));
            console.log('[UNLOAD] Sent beacon to save chat');
        }
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

// Send message with streaming
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    console.log('[API] sendMessage - message:', message.substring(0, 50) + (message.length > 50 ? '...' : ''));

    if (!message || isProcessing) return;

    input.value = '';
    autoResize(input);
    hideWelcome();
    addMessage('user', message, true);  // skipSave: backend handles saving
    showTypingIndicator('Connecting...');
    isProcessing = true;
    document.getElementById('sendBtn').disabled = true;
    showStopButton();

    // Create abort controller for this request
    currentAbortController = new AbortController();

    try {
        console.log('[API] POST /api/chat/stream - workspace:', currentWorkspace, 'chatId:', currentChatId);
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, workspace: currentWorkspace, chatId: currentChatId }),
            signal: currentAbortController.signal
        });

        console.log('[API] Response status:', response.status);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamingCompleted = false;
        let eventCount = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                console.log('[API] Stream complete - total events:', eventCount);
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    eventCount++;
                    if (data.type === 'status') console.log('[API] Status:', data.message);
                    switch (data.type) {
                        case 'status':
                            updateTypingStatus(data.message);
                            break;
                        case 'stream_start':
                            console.log('[API] stream_start');
                            hideTypingIndicator();
                            startStreamingMessage();
                            break;
                        case 'stream':
                            appendStreamingContent(data.content);
                            break;
                        case 'stream_end':
                            console.log('[API] stream_end - content length:', data.content?.length, ', streamingContent length:', streamingContent?.length);
                            // Use data.content if provided and non-empty, otherwise use accumulated streamingContent
                            const finalContent = (data.content && data.content.trim()) ? data.content : streamingContent;
                            console.log('[API] Using finalContent length:', finalContent?.length);
                            finalizeStreamingMessage(finalContent);
                            hideTypingIndicator();
                            streamingCompleted = true;
                            break;
                        case 'response':
                            console.log('[API] response - length:', data.message?.length, 'streamingCompleted:', streamingCompleted);
                            if (!streamingCompleted) {
                                console.log('[API] Adding response via addMessage (streaming was not used)');
                                hideTypingIndicator();
                                addMessage('assistant', data.message);
                            } else {
                                console.log('[API] Skipping response - already handled via streaming');
                            }
                            if (data.workspace && data.workspace !== currentWorkspace) {
                                currentWorkspace = data.workspace;
                                updateWorkspaceDisplay();
                            }
                            break;
                        case 'error':
                            hideTypingIndicator();
                            addMessage('assistant', `❌ Error: ${data.message}`);
                            break;
                        case 'done':
                            // Response complete - immediately re-enable input
                            console.log('[API] done event received');
                            console.log('[API] State: streamingMessageDiv=', !!streamingMessageDiv, ', streamingCompleted=', streamingCompleted, ', chatHistory.length=', chatHistory.length);

                            // Ensure streaming message is finalized if still active
                            if (streamingMessageDiv && !streamingCompleted) {
                                console.log('[API] Finalizing streaming message on done event, content length:', streamingContent?.length);
                                finalizeStreamingMessage(streamingContent);
                                streamingCompleted = true;
                            }

                            isProcessing = false;
                            hideTypingIndicator();
                            const sendBtnDone = document.getElementById('sendBtn');
                            const inputDone = document.getElementById('messageInput');
                            if (sendBtnDone) {
                                sendBtnDone.disabled = false;
                                console.log('[API] Send button enabled');
                            }
                            if (inputDone) {
                                inputDone.disabled = false;
                                inputDone.readOnly = false;
                                inputDone.style.pointerEvents = 'auto';
                                inputDone.focus();
                                console.log('[API] Input field enabled and focused');
                            }
                            hideStopButton();
                            console.log('[API] Done processing complete');
                            break;
                    }
                } catch (e) { /* ignore parse errors */ }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('[API] Request aborted by user');
            hideTypingIndicator();
            // Finalize any streaming message with current content
            if (streamingMessageDiv) {
                finalizeStreamingMessage(streamingContent + '\n\n*[Response stopped by user]*');
            }
        } else {
            console.error('Error:', error);
            hideTypingIndicator();
            addMessage('assistant', '❌ Connection error. Make sure the server is running.');
        }
    } finally {
        // Always reset state, even if there's an error
        console.log('[API] Resetting state in finally block');

        // Ensure streaming message is finalized if still active
        if (streamingMessageDiv) {
            console.log('[API] Finalizing streaming message in finally block');
            finalizeStreamingMessage(streamingContent);
        }

        currentAbortController = null;
        isProcessing = false;

        // Hide typing indicator if still visible
        hideTypingIndicator();

        const sendBtn = document.getElementById('sendBtn');
        const input = document.getElementById('messageInput');
        if (sendBtn) {
            sendBtn.disabled = false;
            console.log('[API] Send button re-enabled');
        }
        if (input) {
            input.disabled = false;
            input.readOnly = false;
            input.style.pointerEvents = 'auto';
            input.focus();
            console.log('[API] Input field re-enabled and focused');
        }
        hideStopButton();
    }
}

// Stop the current streaming request
function stopStreaming() {
    if (currentAbortController) {
        console.log('[API] Stopping stream...');
        currentAbortController.abort();
        // Also notify the backend to stop
        fetch('/api/chat/abort', { method: 'POST' }).catch(() => {});
    }
}

// Show stop button
function showStopButton() {
    const stopBtn = document.getElementById('stopBtn');
    const sendBtn = document.getElementById('sendBtn');
    if (stopBtn) stopBtn.style.display = 'flex';
    if (sendBtn) sendBtn.style.display = 'none';
}

// Hide stop button
function hideStopButton() {
    const stopBtn = document.getElementById('stopBtn');
    const sendBtn = document.getElementById('sendBtn');
    if (stopBtn) stopBtn.style.display = 'none';
    if (sendBtn) sendBtn.style.display = 'flex';
}

// Add message to chat
// skipSave: if true, don't save to server (for streaming where backend handles saving)
function addMessage(role, content, skipSave = false) {
    const container = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    const index = chatHistory.length;
    const messageId = generateMessageId(currentChatId, index, content);

    messageDiv.className = `message ${role}`;
    messageDiv.dataset.messageId = messageId;
    messageDiv.innerHTML = createMessageHTML(role, content, index, messageId);
    container.appendChild(messageDiv);
    addCodeCopyButtons(messageDiv);
    chatHistory.push({ role, content, messageId });
    if (!skipSave) {
        saveCurrentChatToServer();
    }
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
}

// Create message element HTML
function createMessageHTML(role, content, index, messageId = null) {
    const icon = role === 'user' ? 'fa-user' : 'fa-robot';
    const msgId = messageId || generateMessageId(currentChatId, index, content);
    if (role === 'assistant') {
        // Copy button in upper right (inside message-content)
        return `<div class="message-avatar"><i class="fas ${icon}"></i></div>
            <div class="message-content">
                <div class="message-actions">
                    <button class="copy-btn" onclick="copyMessage(this, '${encodeURIComponent(content)}')">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
                <div class="message-text">${formatMessage(content)}</div>
            </div>`;
    } else {
        // Edit button outside the question box (after message-content)
        return `<div class="message-avatar"><i class="fas ${icon}"></i></div>
            <div class="message-content">
                <div class="message-text">${formatMessage(content)}</div>
            </div>
            <div class="message-edit-outside">
                <button class="edit-btn-outside" onclick="editMessage(this, ${index}, '${encodeURIComponent(content)}', '${msgId}')">
                    <i class="fas fa-edit"></i>
                </button>
            </div>`;
    }
}

// Streaming message state
let streamingMessageDiv = null;
let streamingContent = '';
let streamingUpdatePending = false;
let lastStreamingUpdate = 0;

// Start a new streaming message
function startStreamingMessage() {
    console.log('[STREAM] startStreamingMessage called');
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
    streamingFinalized = false;  // Reset finalization flag for new stream
    console.log('[STREAM] streamingMessageDiv created, streamingContent reset, streamingFinalized=false');

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Append content to streaming message with batched updates for performance
function appendStreamingContent(newContent) {
    if (!streamingMessageDiv) return;

    streamingContent += newContent;

    // Batch updates: only update DOM every 50ms for better performance
    const now = Date.now();
    const timeSinceLastUpdate = now - lastStreamingUpdate;

    // Update immediately if it's been a while, or batch small updates
    if (timeSinceLastUpdate > 50 || newContent.includes('\n') || streamingContent.length < 50) {
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

// Actually update the streaming display - lightweight formatting for performance
function updateStreamingDisplay() {
    if (!streamingMessageDiv) return;

    const textDiv = streamingMessageDiv.querySelector('.streaming-text');
    if (textDiv) {
        // Use lightweight formatting during streaming for performance
        // Full formatMessage() is called on finalization
        textDiv.innerHTML = formatMessageLightweight(streamingContent);
    }

    // Scroll to bottom
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

// Lightweight formatting for streaming - minimal processing for speed
function formatMessageLightweight(text) {
    if (!text) return '';
    // Just escape HTML and preserve line breaks - skip expensive parsing
    return escapeHtml(text).replace(/\n/g, '<br>');
}

// Finalize streaming message with complete formatted content
// Track if we've already finalized to prevent double-save
let streamingFinalized = false;

function finalizeStreamingMessage(finalContent) {
    console.log('[STREAM] finalizeStreamingMessage called');
    console.log('[STREAM] streamingMessageDiv exists:', !!streamingMessageDiv, ', streamingFinalized:', streamingFinalized);
    console.log('[STREAM] finalContent length:', finalContent?.length || 0, ', streamingContent length:', streamingContent?.length || 0);

    // Prevent double finalization
    if (streamingFinalized) {
        console.log('[STREAM] Already finalized, skipping');
        return;
    }

    if (!streamingMessageDiv) {
        console.log('[STREAM] No streamingMessageDiv, skipping');
        return;
    }

    // Mark as finalized immediately to prevent race conditions
    streamingFinalized = true;

    const container = document.getElementById('chatMessages');

    // Remove streaming class and cursor
    streamingMessageDiv.classList.remove('streaming');
    const cursor = streamingMessageDiv.querySelector('.streaming-cursor');
    if (cursor) cursor.remove();

    // Get the text div and current streamed content
    const textDiv = streamingMessageDiv.querySelector('.streaming-text');

    // Use finalContent if provided, otherwise keep the streamed content
    const contentToUse = finalContent && finalContent.trim() ? finalContent : (streamingContent || '');

    console.log('[STREAM] contentToUse length:', contentToUse?.length || 0);

    if (!contentToUse || !contentToUse.trim()) {
        console.log('[STREAM] WARNING: No content to save!');
    }

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

    // Add to local history (for UI display)
    // Note: Backend saves the assistant response to MongoDB
    console.log('[STREAM] Adding assistant message to local chatHistory');
    const index = chatHistory.length;
    const messageId = generateMessageId(currentChatId, index, contentToUse);
    streamingMessageDiv.dataset.messageId = messageId;
    chatHistory.push({ role: 'assistant', content: contentToUse, messageId });
    console.log('[STREAM] chatHistory now has', chatHistory.length, 'messages');

    // Refresh sidebar to show updated chat
    loadChatsFromServer();

    // Reset streaming state
    streamingMessageDiv = null;
    streamingContent = '';
    console.log('[STREAM] Streaming state reset complete');

    // Final scroll
    container.scrollTop = container.scrollHeight;
}

// Edit and resubmit a user message
// messageId is used to identify the exact message being edited
function editMessage(btn, messageIndex, encodedContent, messageId = null) {
    if (isProcessing) {
        return; // Don't allow editing while processing
    }

    const content = decodeURIComponent(encodedContent);
    const container = document.getElementById('chatMessages');
    const messages = container.querySelectorAll('.message');

    // Find the message element - use messageId if available for precise matching
    let userMessageEl = btn.closest('.message');
    let userMessageIdx = Array.from(messages).indexOf(userMessageEl);

    // If messageId is provided, find the exact message by ID
    if (messageId) {
        const matchingEl = container.querySelector(`[data-message-id="${messageId}"]`);
        if (matchingEl) {
            userMessageEl = matchingEl;
            userMessageIdx = Array.from(messages).indexOf(matchingEl);
        }

        // Also find the index in chatHistory by messageId
        const historyIdx = chatHistory.findIndex(msg => msg.messageId === messageId);
        if (historyIdx !== -1) {
            messageIndex = historyIdx;
        }
    }

    console.log(`[EDIT] Editing message at index ${messageIndex}, messageId: ${messageId}`);

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
    // This removes the edited question and all subsequent Q&A pairs
    chatHistory = chatHistory.slice(0, messageIndex);
    console.log(`[EDIT] Chat history truncated to ${chatHistory.length} messages`);
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

// ============================================================================
// TOOL FORMATTING CONFIG - Edit this section when changing AI providers
// ============================================================================
const TOOL_CONFIG = {
    // Tools: name, icon, type (for styling)
    tools: [
        { name: 'Terminal', icon: 'fa-terminal', type: 'terminal' },
        { name: 'Read Directory', icon: 'fa-folder-open', type: 'read' },
        { name: 'Read File', icon: 'fa-file-code', type: 'read' },
        { name: 'Read Process', icon: 'fa-stream', type: 'read' },
        { name: 'Write File', icon: 'fa-file-pen', type: 'action' },
        { name: 'Edit File', icon: 'fa-edit', type: 'action' },
        { name: 'Search', icon: 'fa-search', type: 'action' },
        { name: 'Codebase Search', icon: 'fa-code', type: 'action' },
        { name: 'Web Search', icon: 'fa-globe', type: 'action' },
    ],
    // Result line prefix
    resultPrefix: '↳',
    // Result status keywords that END a tool block (case insensitive)
    resultEndKeywords: [
        'command completed', 'command error', 'listed', 'read',
        'process completed', 'wrote', 'edited', 'found', 'no results'
    ],
};

// Check if a result line indicates successful end of tool output
function isSuccessEndLine(text) {
    const lower = text.toLowerCase();
    const successKeywords = ['command completed', 'listed', 'read', 'process completed', 'wrote', 'edited', 'found'];
    return successKeywords.some(kw => lower.includes(kw));
}

// Check if a result line indicates error start (we should collect more lines after this)
function isErrorStartLine(text) {
    const lower = text.toLowerCase();
    return lower.includes('command error') || lower.includes('traceback');
}

// Check if a line looks like part of a stack trace or error output
function isStackTraceLine(text) {
    const trimmed = text.trim();
    // Stack trace patterns: File "...", line numbers, exception names, indented code
    return /^(File\s+"|Traceback|[A-Z][a-zA-Z]*Error:|[A-Z][a-zA-Z]*Exception:|OSError:|KeyError:|ValueError:|TypeError:|AttributeError:|ImportError:|ModuleNotFoundError:|RuntimeError:|IndexError:|NameError:|SyntaxError:|\s{2,}|\d+\s*\||at\s+|in\s+<)/.test(trimmed) ||
           trimmed.startsWith('app.run') ||
           trimmed.startsWith('run_simple') ||
           trimmed.includes('site-packages') ||
           trimmed.includes('.py", line') ||
           trimmed.includes('.py", line');
}

// Check if line looks like explanatory text (not stack trace)
function isExplanatoryText(text) {
    const trimmed = text.trim();
    if (!trimmed) return false;
    // Explanatory text usually starts with capital letter and forms a sentence
    // or starts with "This", "The", "Let me", "I'll", etc.
    const explanatoryStarts = ['this ', 'the ', 'let me', "i'll", 'there', 'it ', 'now ', 'would you', 'you can'];
    const lower = trimmed.toLowerCase();
    return explanatoryStarts.some(s => lower.startsWith(s));
}

// Cached regex for tool parsing - built once for performance
let _cachedToolStartRegex = null;
function getToolStartRegex() {
    if (!_cachedToolStartRegex) {
        const toolNames = TOOL_CONFIG.tools.map(t => t.name).join('|');
        _cachedToolStartRegex = new RegExp(`^(${toolNames})\\s+-\\s+(.+)$`);
    }
    return _cachedToolStartRegex;
}

// Parse tool blocks from text - accurate boundary detection
function parseToolBlocks(text) {
    const lines = text.split('\n');
    const result = [];
    let i = 0;

    // Use cached regex for performance
    const toolStartRegex = getToolStartRegex();

    while (i < lines.length) {
        const line = lines[i];
        const toolMatch = line.match(toolStartRegex);

        if (toolMatch) {
            const [, toolName, firstLine] = toolMatch;
            const toolConfig = TOOL_CONFIG.tools.find(t => t.name === toolName);

            // Collect command lines until we hit a result line
            let commandLines = [firstLine];
            let resultLines = [];
            let hasError = false;
            let inStackTrace = false;
            let foundEndResult = false;
            i++;

            while (i < lines.length && !foundEndResult) {
                const nextLine = lines[i];
                const trimmed = nextLine.trim();

                // Check if this is a result line (starts with ↳)
                if (trimmed.startsWith(TOOL_CONFIG.resultPrefix)) {
                    const resultContent = trimmed.substring(1).trim();
                    resultLines.push(resultContent);

                    // Track if we have an error/traceback starting
                    if (isErrorStartLine(resultContent)) {
                        hasError = true;
                        inStackTrace = true;
                    }

                    // Only end on success keywords (not error)
                    if (isSuccessEndLine(resultContent) && !hasError) {
                        foundEndResult = true;
                    }
                    i++;
                }
                // Check if new tool is starting
                else if (toolStartRegex.test(nextLine)) {
                    break; // New tool starting, end current block
                }
                // Empty line
                else if (trimmed === '') {
                    if (resultLines.length > 0 && !inStackTrace) {
                        break;
                    }
                    i++;
                }
                // If we're in a stack trace, collect continuation lines
                else if (inStackTrace) {
                    // Check if this looks like explanatory text (end of stack trace)
                    if (isExplanatoryText(trimmed)) {
                        inStackTrace = false;
                        break;
                    }
                    // Otherwise it's part of the stack trace
                    resultLines.push(trimmed);
                    i++;
                }
                // Otherwise it's continuation of command (before any results)
                else if (resultLines.length === 0) {
                    commandLines.push(nextLine);
                    i++;
                }
                // Text after results = end of block
                else {
                    break;
                }
            }

            result.push({
                type: 'tool',
                toolType: toolConfig.type,
                name: toolConfig.name,
                icon: toolConfig.icon,
                command: commandLines.join('\n').trim(),
                results: resultLines,
                hasError: hasError
            });
            continue;
        }

        // Standalone result line (orphaned ↳)
        if (line.trim().startsWith(TOOL_CONFIG.resultPrefix)) {
            result.push({
                type: 'result',
                content: line.trim().substring(1).trim()
            });
            i++;
            continue;
        }

        // Regular text
        result.push({ type: 'text', content: line });
        i++;
    }

    return result;
}

// Render a tool block to HTML
function renderToolBlock(tool) {
    const typeClass = `tool-${tool.toolType}`;
    const errorClass = tool.hasError ? ' has-error' : '';
    let html = `<div class="tool-block ${typeClass}${errorClass}">`;
    html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
    html += `<div class="tool-command"><code>${escapeHtml(tool.command)}</code></div>`;

    if (tool.results.length > 0) {
        // Check if this is an error with stack trace
        const hasStackTrace = tool.results.some(r =>
            r.toLowerCase().includes('traceback') ||
            r.toLowerCase().includes('file "') ||
            r.match(/^\s*(File|Line|\w+Error:)/i)
        );

        if (tool.hasError && hasStackTrace) {
            // Render as a formatted error block
            html += `<div class="tool-result error-block">`;
            html += `<div class="error-header"><i class="fas fa-exclamation-triangle"></i> Error Output</div>`;
            html += `<pre class="stack-trace">`;
            tool.results.forEach(r => {
                html += escapeHtml(r) + '\n';
            });
            html += `</pre></div>`;
        } else {
            // Normal result rendering
            html += `<div class="tool-result">`;
            tool.results.forEach(r => {
                let resultHtml = escapeHtml(r);
                if (r.toLowerCase().includes('error')) {
                    resultHtml = `<span class="result-error">${resultHtml}</span>`;
                } else if (r.toLowerCase().includes('completed')) {
                    resultHtml = `<span class="result-success">${resultHtml}</span>`;
                }
                html += `<div class="result-line"><span class="result-arrow">↳</span> ${resultHtml}</div>`;
            });
            html += `</div>`;
        }
    }
    html += `</div>`;
    return html;
}

// Helper to escape HTML
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Format message with code blocks and markdown
function formatMessage(text) {
    if (!text) return '';

    // Normalize line endings
    text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // Extract and protect code blocks BEFORE escaping (they have their own escaping)
    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code></pre>`);
        return `__CODE_BLOCK_${index}__`;
    });

    // Extract and protect inline code
    const inlineCodes = [];
    text = text.replace(/`([^`]+)`/g, (match, code) => {
        const index = inlineCodes.length;
        inlineCodes.push(`<code>${escapeHtml(code)}</code>`);
        return `__INLINE_CODE_${index}__`;
    });

    // Parse tool blocks BEFORE escaping (renderToolBlock handles escaping)
    const parsed = parseToolBlocks(text);

    // Rebuild text with formatted tool blocks
    const toolBlocks = [];
    const rebuiltLines = [];

    for (const item of parsed) {
        if (item.type === 'tool') {
            const index = toolBlocks.length;
            toolBlocks.push(renderToolBlock(item));
            rebuiltLines.push(`__TOOL_BLOCK_${index}__`);
        } else if (item.type === 'result') {
            const index = toolBlocks.length;
            toolBlocks.push(`<div class="tool-result standalone"><span class="result-arrow">↳</span> ${escapeHtml(item.content)}</div>`);
            rebuiltLines.push(`__TOOL_BLOCK_${index}__`);
        } else {
            // Escape regular text lines
            rebuiltLines.push(escapeHtml(item.content));
        }
    }
    text = rebuiltLines.join('\n');

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

    // Bold and Italic
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // Lists
    const lines = text.split('\n');
    let inList = false;
    let listType = null;
    const processedLines = [];

    for (const line of lines) {
        const bulletMatch = line.match(/^[\s]*[•\-\*]\s+(.+)$/);
        const numberedMatch = line.match(/^[\s]*(\d+)\.\s+(.+)$/);

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
        } else {
            if (inList) {
                processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
                inList = false;
                listType = null;
            }
            processedLines.push(line);
        }
    }
    if (inList) processedLines.push(listType === 'ul' ? '</ul>' : '</ol>');
    text = processedLines.join('\n');

    // Paragraph and line breaks
    text = text.replace(/\n\n+/g, '</p><p>');
    text = text.replace(/(?<!<\/(?:h[1-6]|p|ul|ol|li|table|thead|tbody|tr|th|td|pre|div)>)\n(?!<)/g, '<br>');
    text = '<p>' + text + '</p>';

    // Clean up
    text = text.replace(/<p>\s*<\/p>/g, '');
    text = text.replace(/<p>\s*<(ul|ol|table|h[1-6]|pre)/g, '<$1');
    text = text.replace(/<\/(ul|ol|table|h[1-6]|pre)>\s*<\/p>/g, '</$1>');

    // Restore protected blocks
    toolBlocks.forEach((block, i) => { text = text.replace(`__TOOL_BLOCK_${i}__`, block); });
    codeBlocks.forEach((block, i) => { text = text.replace(`__CODE_BLOCK_${i}__`, block); });
    inlineCodes.forEach((code, i) => { text = text.replace(`__INLINE_CODE_${i}__`, code); });

    // Clean up tool blocks in paragraphs
    text = text.replace(/<p>(<div class="tool-block)/g, '$1');
    text = text.replace(/(<\/div>)<\/p>/g, '$1');
    text = text.replace(/<br>(<div class="tool-)/g, '$1');
    text = text.replace(/(<\/div>)<br>/g, '$1');

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

    // Remove existing status log and typing indicator
    document.getElementById('statusLog')?.remove();
    document.getElementById('typingIndicator')?.remove();

    // Create status log
    const statusLogDiv = document.createElement('div');
    statusLogDiv.className = 'status-log';
    statusLogDiv.id = 'statusLog';
    statusLogDiv.innerHTML = `
        <div class="status-generic" id="statusGeneric">
            <i class="fas fa-circle-notch fa-spin"></i> <span id="genericStatusText">${statusMessage}</span>
        </div>
        <div class="status-details" id="statusDetails"></div>
    `;
    container.appendChild(statusLogDiv);

    // Create typing indicator
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="typing-indicator"><div class="typing-dots"><span></span><span></span><span></span></div></div>
        </div>
    `;
    container.appendChild(typingDiv);
    setTimeout(() => container.scrollTop = container.scrollHeight, 50);
}

// Get current status log
function getCurrentStatusLog() {
    const logs = document.querySelectorAll('.status-log:not(.complete)');
    return logs.length > 0 ? logs[logs.length - 1] : null;
}

// Update typing status
function updateTypingStatus(message) {
    const statusLog = getCurrentStatusLog();
    if (!statusLog) return;

    const isGeneric = genericStatuses.some(g => message.includes(g) || g.includes(message));
    if (isGeneric) {
        const genericText = statusLog.querySelector('#genericStatusText');
        if (genericText) genericText.textContent = message;
    } else {
        const statusDetails = statusLog.querySelector('#statusDetails');
        if (statusDetails) {
            const isSubAction = message.trim().startsWith('↳') || message.trim().startsWith('⎿');
            const statusItem = document.createElement('div');
            statusItem.className = isSubAction ? 'status-item sub-action' : 'status-item';
            statusItem.innerHTML = isSubAction
                ? `<i class="fas fa-check"></i> ${message.trim()}`
                : `<i class="fas fa-circle-notch fa-spin"></i> ${message}`;
            statusDetails.appendChild(statusItem);
        }
    }
    setTimeout(() => document.getElementById('chatMessages').scrollTop = document.getElementById('chatMessages').scrollHeight, 50);
}

function hideTypingIndicator() {
    document.getElementById('typingIndicator')?.remove();
    getCurrentStatusLog()?.remove();
    document.querySelectorAll('.status-log.complete').forEach(log => log.remove());
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
        document.getElementById('chatMessages').innerHTML = WELCOME_HTML;
        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to create chat:', error);
        showNotification('Failed to create new chat');
    }
}

// Save current chat to server
async function saveCurrentChatToServer() {
    console.log('[SAVE] saveCurrentChatToServer called, chatId:', currentChatId, ', history length:', chatHistory.length);
    if (!currentChatId || chatHistory.length === 0) return;

    try {
        console.log('[SAVE] Saving', chatHistory.length, 'messages to server');
        await fetch(`/api/chats/${currentChatId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatHistory })
        });
        console.log('[SAVE] Save successful');

        loadChatsFromServer();
    } catch (error) {
        console.error('[SAVE] Failed to save chat:', error);
    }
}

// Load chat from server
async function loadChatFromServer(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        const chat = await response.json();
        if (chat.error) {
            // Chat not found - create a new one
            console.log('[LOAD] Chat not found, creating new chat');
            localStorage.removeItem('currentChatId');
            await createNewChat();
            return;
        }

        currentChatId = chatId;
        chatHistory = chat.messages || [];
        localStorage.setItem('currentChatId', currentChatId);

        const container = document.getElementById('chatMessages');
        container.innerHTML = '';

        if (chatHistory.length === 0) {
            container.innerHTML = WELCOME_HTML;
        } else {
            chatHistory.forEach((msg, idx) => {
                // Generate messageId if not present (for backward compatibility)
                if (!msg.messageId) {
                    msg.messageId = generateMessageId(currentChatId, idx, msg.content);
                }
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${msg.role}`;
                messageDiv.dataset.messageId = msg.messageId;
                messageDiv.innerHTML = createMessageHTML(msg.role, msg.content, idx, msg.messageId);
                container.appendChild(messageDiv);
                addCodeCopyButtons(messageDiv);
            });
            setTimeout(() => container.scrollTop = container.scrollHeight, 50);
        }
        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to load chat:', error);
        // On error, create a new chat
        localStorage.removeItem('currentChatId');
        await createNewChat();
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

