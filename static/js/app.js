// Chat Application JavaScript - Powered by Augment Code

let chatHistory = [];
let currentChatId = null;
let isProcessing = false;
let currentWorkspace = '~';
let currentModel = 'claude-opus-4.5';
let availableModels = [];
let browserCurrentPath = '';
let sidebarOpen = true;
let currentAbortController = null;
let historyEnabled = true;  // Global toggle for chat history storage

// Network request/response logger
function logRequest(method, url, body = null) {
    const fullUrl = new URL(url, window.location.origin).href;
    const bodyStr = body ? JSON.stringify(body).substring(0, 500) : 'None';
    console.log(`[REQUEST] ${method} ${fullUrl} | Body: ${bodyStr}`);
}

function logResponse(method, url, status, body = null) {
    const fullUrl = new URL(url, window.location.origin).href;
    const bodyStr = body ? JSON.stringify(body).substring(0, 500) : 'None';
    console.log(`[RESPONSE] ${method} ${fullUrl} | Status: ${status} | Body: ${bodyStr}`);
}

// Generate a unique message ID based on chatId, index, and random UUID
function generateMessageId(chatId, index, content) {
    // Use crypto.randomUUID() or fallback to random hex
    const uniqueSuffix = (crypto.randomUUID ? crypto.randomUUID().substring(0, 8) :
        Math.random().toString(16).substring(2, 10));
    return `${chatId}-${index}-${uniqueSuffix}`;
}

// Shared welcome message HTML
const WELCOME_HTML = `
    <div class="welcome-message">
        <h2>What can I help you with?</h2>
        <div class="quick-actions">
            <button class="action-btn" onclick="sendSuggestion('Show me the folder structure of this project')">
                <i class="fas fa-sitemap"></i> Project structure
            </button>
            <button class="action-btn" onclick="sendSuggestion('List all files in the current directory')">
                <i class="fas fa-folder-tree"></i> List files
            </button>
            <button class="action-btn" onclick="sendSuggestion('Check if any application is running on port 5000 and show me the process details')">
                <i class="fas fa-server"></i> Check port
            </button>
            <button class="action-btn" onclick="sendSuggestion('Write a Python function to check if a number is prime and test it with examples')">
                <i class="fas fa-code"></i> Write code
            </button>
            <button class="action-btn" onclick="sendSuggestion('Find all TODO comments in this project and list them with their file locations')">
                <i class="fas fa-search"></i> Find TODOs
            </button>
            <button class="action-btn" onclick="sendSuggestion('Show me the git status and recent commits in this repository')">
                <i class="fas fa-code-branch"></i> Git status
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

// Load settings from server
async function loadSettingsFromServer() {
    const url = '/api/settings';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        if (data.workspace) {
            currentWorkspace = data.workspace;
            updateWorkspaceDisplay();
        }
        if (data.model) {
            currentModel = data.model;
        }
        if (data.available_models) {
            availableModels = data.available_models;
            populateModelSelect();
        }
        // Handle history_enabled setting
        if (typeof data.history_enabled !== 'undefined') {
            historyEnabled = data.history_enabled;
            updateHistoryToggle();
            updateSidebarVisibility();
        }
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

// Update history toggle checkbox state
function updateHistoryToggle() {
    const toggle = document.getElementById('historyToggle');
    if (toggle) {
        toggle.checked = historyEnabled;
        // Add change listener for auto-save
        toggle.onchange = async function() {
            historyEnabled = this.checked;
            updateSidebarVisibility();
            // Save to server immediately
            const url = '/api/settings';
            const requestBody = { workspace: currentWorkspace, model: currentModel, history_enabled: historyEnabled };
            try {
                await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                console.log('[historyToggle] History setting updated to:', historyEnabled);
                showNotification(historyEnabled ? 'Chat history enabled' : 'Chat history disabled');
            } catch (error) {
                console.error('Failed to update history setting:', error);
            }
        };
    }
}

// Show/hide sidebar based on history setting
function updateSidebarVisibility() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        if (historyEnabled) {
            sidebar.style.display = '';
            sidebar.classList.remove('history-disabled');
        } else {
            sidebar.classList.add('history-disabled');
        }
    }
}

// Populate model select dropdown (both header and settings modal)
function populateModelSelect() {
    const select = document.getElementById('modelSelect');
    const headerSelect = document.getElementById('modelSelectHeader');

    [select, headerSelect].forEach(sel => {
        if (!sel) return;
        sel.innerHTML = '';
        availableModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === currentModel) {
                option.selected = true;
            }
            sel.appendChild(option);
        });
    });
}

// Update model from header select and save immediately
async function updateModelFromHeader() {
    const headerSelect = document.getElementById('modelSelectHeader');
    const modalSelect = document.getElementById('modelSelect');
    if (!headerSelect) return;

    const model = headerSelect.value;
    currentModel = model;

    // Sync with modal select
    if (modalSelect) {
        modalSelect.value = model;
    }

    // Save to server immediately
    const url = '/api/settings';
    const requestBody = { workspace: currentWorkspace, model: model, history_enabled: historyEnabled };
    try {
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        console.log('[updateModelFromHeader] Model updated to:', model);
    } catch (error) {
        console.error('Failed to update model:', error);
    }
}

// Legacy alias for compatibility
function loadWorkspaceFromServer() {
    return loadSettingsFromServer();
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
    const url = '/api/check-auth';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
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

// Request ID to track active requests and ignore events from stale requests
let currentRequestId = 0;

// Send message with streaming
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message || isProcessing) return;

    // Increment request ID - this invalidates any previous request
    currentRequestId++;
    const thisRequestId = currentRequestId;
    console.log(`[API] Starting request #${thisRequestId}`);

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

    const url = '/api/chat/stream';
    const requestBody = { message, workspace: currentWorkspace, chatId: currentChatId };
    logRequest('POST', url, requestBody);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
            signal: currentAbortController.signal
        });

        logResponse('POST', url, response.status, 'SSE stream initiated');

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

                // CRITICAL: Check if this request is still current
                // If a new request has started, ignore events from this stale request
                if (thisRequestId !== currentRequestId) {
                    console.log(`[API] IGNORING event from stale request #${thisRequestId} (current is #${currentRequestId})`);
                    continue;
                }

                try {
                    const data = JSON.parse(line.slice(6));
                    eventCount++;

                    switch (data.type) {
                        case 'status':
                            updateTypingStatus(data.message);
                            break;
                        case 'stream_start':
                            console.log(`[API] Request #${thisRequestId} stream_start`);
                            hideTypingIndicator();
                            startStreamingMessage(thisRequestId);
                            break;
                        case 'stream':
                            appendStreamingContent(data.content, thisRequestId);
                            break;
                        case 'stream_end':
                            console.log(`[API] Request #${thisRequestId} stream_end - content length:`, data.content?.length, ', streamingContent length:', streamingContent?.length);
                            // Use data.content if provided and non-empty, otherwise use accumulated streamingContent
                            const finalContent = (data.content && data.content.trim()) ? data.content : streamingContent;
                            console.log('[API] Using finalContent length:', finalContent?.length);
                            finalizeStreamingMessage(finalContent, thisRequestId);
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
                        case 'aborted':
                            // Request was aborted (e.g., due to edit/retry)
                            console.log('[API] Request aborted by server');
                            hideTypingIndicator();
                            // Remove any partial streaming message
                            if (streamingMessageDiv) {
                                streamingMessageDiv.remove();
                                streamingMessageDiv = null;
                            }
                            streamingContent = '';
                            streamingFinalized = true;  // Prevent any further finalization
                            break;
                        case 'done':
                            // Response complete - immediately re-enable input
                            console.log('[API] done event received');
                            console.log('[API] State: streamingMessageDiv=', !!streamingMessageDiv, ', streamingCompleted=', streamingCompleted, ', chatHistory.length=', chatHistory.length);

                            // Ensure streaming message is finalized if still active
                            if (streamingMessageDiv && !streamingCompleted) {
                                console.log('[API] Finalizing streaming message on done event, content length:', streamingContent?.length);
                                finalizeStreamingMessage(streamingContent, thisRequestId);
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
            console.log(`[API] Request #${thisRequestId} aborted by user`);
            // Only cleanup if this is still the current request
            if (thisRequestId === currentRequestId) {
                hideTypingIndicator();
                // DON'T finalize - just remove any partial streaming message
                // This prevents old content from appearing when aborting for edit/retry
                if (streamingMessageDiv) {
                    console.log('[API] Removing partial streaming message due to abort');
                    streamingMessageDiv.remove();
                    streamingMessageDiv = null;
                    streamingContent = '';
                    streamingFinalized = true;
                }
            } else {
                console.log(`[API] Request #${thisRequestId} was stale, skipping cleanup`);
            }
        } else {
            console.error('Error:', error);
            hideTypingIndicator();
            addMessage('assistant', '❌ Connection error. Make sure the server is running.');
        }
    } finally {
        console.log(`[API] Request #${thisRequestId} finally block, currentRequestId=${currentRequestId}, streamingFinalized=`, streamingFinalized);

        // CRITICAL: Only do cleanup if this is still the current request
        // Stale requests should not touch any state
        if (thisRequestId !== currentRequestId) {
            console.log(`[API] Request #${thisRequestId} is stale, skipping finally cleanup`);
            return;
        }

        // Only finalize if not already finalized (prevents double-finalization on abort)
        if (streamingMessageDiv && !streamingFinalized) {
            console.log('[API] Finalizing streaming message in finally block');
            finalizeStreamingMessage(streamingContent, thisRequestId);
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
        const url = '/api/chat/abort';
        logRequest('POST', url);
        currentAbortController.abort();
        // Also notify the backend to stop
        fetch(url, { method: 'POST' })
            .then(response => response.json())
            .then(data => logResponse('POST', url, 200, data))
            .catch(() => {});
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
        // Edit and copy buttons outside the box, bottom right
        const encodedContent = btoa(unescape(encodeURIComponent(content)));
        return `<div class="message-avatar"><i class="fas ${icon}"></i></div>
            <div class="message-content">
                <div class="message-text">${formatMessage(content)}</div>
            </div>
            <div class="message-actions-outside">
                <button class="user-copy-btn" data-content="${encodedContent}" title="Copy message">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="edit-btn-outside" data-content="${encodedContent}" data-index="${index}" data-msgid="${msgId}" title="Edit message">
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

// Track which request owns the current streaming message
let streamingRequestId = null;

// Start a new streaming message
function startStreamingMessage(requestId) {
    console.log(`[STREAM] startStreamingMessage called for request #${requestId}, currentRequestId=${currentRequestId}`);

    // Only start if this is still the current request
    if (requestId !== currentRequestId) {
        console.log(`[STREAM] IGNORING startStreamingMessage - stale request #${requestId}`);
        return;
    }

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
    streamingRequestId = requestId;  // Track which request owns this stream
    resetIncrementalFormatCache();  // Reset formatting cache for new stream
    console.log(`[STREAM] streamingMessageDiv created for request #${requestId}, streamingContent reset, streamingFinalized=false`);

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Append content to streaming message with batched updates for performance
function appendStreamingContent(newContent, requestId) {
    // Ignore if this is from a stale request
    if (requestId !== currentRequestId || requestId !== streamingRequestId) {
        console.log(`[STREAM] IGNORING appendStreamingContent - stale request #${requestId} (current=#${currentRequestId}, streaming=#${streamingRequestId})`);
        return;
    }

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

// Actually update the streaming display - incremental formatting for live preview
function updateStreamingDisplay() {
    if (!streamingMessageDiv) return;

    const textDiv = streamingMessageDiv.querySelector('.streaming-text');
    if (textDiv) {
        // Use incremental formatting for live preview of tables, code, etc.
        textDiv.innerHTML = formatMessageIncremental(streamingContent);
    }

    // Scroll to bottom
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

// Incremental formatting for streaming - formats complete structures on-the-fly
// Cache for incremental formatting to avoid re-processing
let incrementalFormatCache = {
    lastInput: '',
    lastOutput: '',
    completedBlocks: 0
};

function formatMessageIncremental(text) {
    if (!text) return '';

    // If text is shorter than cached (user edited/reset), clear cache
    if (text.length < incrementalFormatCache.lastInput.length) {
        incrementalFormatCache = { lastInput: '', lastOutput: '', completedBlocks: 0 };
    }

    // Quick check: if nothing changed, return cached
    if (text === incrementalFormatCache.lastInput) {
        return incrementalFormatCache.lastOutput;
    }

    // Split into complete lines and incomplete trailing line
    const lines = text.split('\n');
    const hasIncompleteLastLine = !text.endsWith('\n');
    const incompleteLine = hasIncompleteLastLine ? lines.pop() : '';
    const completeText = lines.join('\n');

    // Format complete structures
    let formatted = formatCompleteStructures(completeText);

    // Append incomplete line as plain escaped text
    if (incompleteLine) {
        formatted += (formatted ? '<br>' : '') + escapeHtml(incompleteLine);
    }

    // Cache result
    incrementalFormatCache.lastInput = text;
    incrementalFormatCache.lastOutput = formatted;

    return formatted;
}

// Format only complete markdown structures (tables, code blocks, lists, etc.)
function formatCompleteStructures(text) {
    if (!text) return '';

    let result = text;

    // Handle complete code blocks (``` ... ```)
    const codeBlocks = [];
    result = result.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const idx = codeBlocks.length;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code></pre>`);
        return `__CODEBLOCK_${idx}__`;
    });

    // Handle incomplete code blocks - show as plain text with indicator
    result = result.replace(/```(\w+)?\n([\s\S]*)$/g, (match, lang, code) => {
        const idx = codeBlocks.length;
        const langLabel = lang ? `<span class="code-lang">${lang}</span>` : '';
        codeBlocks.push(`<pre class="streaming-code">${langLabel}<code>${escapeHtml(code)}</code><span class="code-cursor">▋</span></pre>`);
        return `__CODEBLOCK_${idx}__`;
    });

    // Handle inline code
    result = result.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // Escape HTML for remaining text (but preserve our placeholders)
    const parts = result.split(/(__CODEBLOCK_\d+__)/);
    result = parts.map(part => {
        if (part.match(/__CODEBLOCK_\d+__/)) return part;
        return escapeHtml(part);
    }).join('');

    // Handle complete tables (header + separator + at least one row)
    result = result.replace(/^(\|.+\|)\n(\|[-:\s|]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, separator, body) => {
        try {
            const headerCells = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            return `<table class="md-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table>`;
        } catch (e) {
            return match;
        }
    });

    // Headers
    result = result.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    result = result.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    result = result.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold and Italic
    result = result.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // Simple list handling - convert existing markdown lists
    result = result.replace(/^[\s]*[-•]\s+(.+)$/gm, '<li class="stream-li">$1</li>');
    result = result.replace(/^[\s]*(\d+)\.\s+(.+)$/gm, '<li class="stream-li-num">$1. $2</li>');

    // Terminal-style bullet points: add ~ only to the FIRST line of each paragraph
    // Skip lines that are already formatted or are continuations of previous lines
    const lines = result.split('\n');
    let prevWasEmpty = true;  // Track if previous line was empty (for paragraph detection)
    const formattedLines = lines.map((line, idx) => {
        const trimmed = line.trim();

        // Skip empty lines (mark for next iteration)
        if (!trimmed) {
            prevWasEmpty = true;
            return line;
        }

        // Skip already formatted elements
        if (trimmed.startsWith('<h') ||
            trimmed.startsWith('<li') ||
            trimmed.startsWith('<table') ||
            trimmed.startsWith('<tr') ||
            trimmed.startsWith('<th') ||
            trimmed.startsWith('<td') ||
            trimmed.startsWith('__CODEBLOCK_') ||
            trimmed.startsWith('|') ||
            trimmed.match(/^[-=]{3,}$/)) {
            prevWasEmpty = false;
            return line;
        }

        // Only add bullet to FIRST line of a paragraph (after empty line or at start)
        const shouldAddBullet = prevWasEmpty;
        prevWasEmpty = false;

        if (shouldAddBullet) {
            return `<span class="stream-bullet">~</span> ${line}`;
        }
        return line;
    });
    result = formattedLines.join('\n');

    // Line breaks
    result = result.replace(/\n/g, '<br>');

    // Restore code blocks
    codeBlocks.forEach((block, idx) => {
        result = result.replace(`__CODEBLOCK_${idx}__`, block);
    });

    return result;
}

// Reset incremental format cache (call when starting new stream)
function resetIncrementalFormatCache() {
    incrementalFormatCache = { lastInput: '', lastOutput: '', completedBlocks: 0 };
}

// Finalize streaming message with complete formatted content
// Track if we've already finalized to prevent double-save
let streamingFinalized = false;

function finalizeStreamingMessage(finalContent, requestId) {
    console.log(`[STREAM] finalizeStreamingMessage called for request #${requestId}`);
    console.log(`[STREAM] currentRequestId=${currentRequestId}, streamingRequestId=${streamingRequestId}`);
    console.log('[STREAM] streamingMessageDiv exists:', !!streamingMessageDiv, ', streamingFinalized:', streamingFinalized);
    console.log('[STREAM] finalContent length:', finalContent?.length || 0, ', streamingContent length:', streamingContent?.length || 0);

    // Ignore if this is from a stale request
    if (requestId !== undefined && requestId !== currentRequestId) {
        console.log(`[STREAM] IGNORING finalizeStreamingMessage - stale request #${requestId}`);
        return;
    }

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

    console.log(`[EDIT] Starting inline edit at index ${messageIndex}, messageId: ${messageId}`);

    // Store original content for cancel
    const originalContent = content;
    const originalHTML = userMessageEl.innerHTML;

    // Replace message content with editable textarea and buttons
    const contentDiv = userMessageEl.querySelector('.message-content');
    const actionsOutside = userMessageEl.querySelector('.message-actions-outside');
    const textDiv = contentDiv.querySelector('.message-text');

    // Capture the original dimensions BEFORE any changes
    const originalContentWidth = contentDiv.offsetWidth;
    const originalTextHeight = textDiv.offsetHeight;
    const originalStyles = {
        minWidth: contentDiv.style.minWidth,
        width: contentDiv.style.width
    };

    // Hide the action buttons and add editing class
    if (actionsOutside) actionsOutside.style.display = 'none';
    userMessageEl.classList.add('editing');

    // Save original text HTML before replacing
    const originalTextHTML = textDiv.innerHTML;

    // Replace message text with textarea
    textDiv.innerHTML = `
        <textarea class="edit-textarea">${escapeHtml(content)}</textarea>
        <div class="edit-buttons">
            <button class="edit-cancel-btn" title="Cancel (Esc)">
                Cancel
            </button>
            <button class="edit-submit-btn" title="Submit (Enter)">
                Submit
            </button>
        </div>
    `;

    const textarea = textDiv.querySelector('.edit-textarea');
    const submitBtn = textDiv.querySelector('.edit-submit-btn');
    const cancelBtn = textDiv.querySelector('.edit-cancel-btn');

    // Set textarea width to match original content width
    const minWidth = Math.max(originalContentWidth, 280);
    textarea.style.width = minWidth + 'px';
    contentDiv.style.minWidth = minWidth + 'px';

    // Let the textarea auto-size based on content using scrollHeight
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
    const initialHeight = textarea.scrollHeight;

    // Auto-resize textarea when user types
    const autoResizeTextarea = () => {
        textarea.style.height = 'auto';
        const newHeight = Math.min(Math.max(textarea.scrollHeight, initialHeight), 200);
        textarea.style.height = newHeight + 'px';
    };

    // Focus
    textarea.focus();

    // Move cursor to end
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    textarea.addEventListener('input', autoResizeTextarea);

    // Cancel button - restore original state
    cancelBtn.onclick = () => {
        console.log(`[EDIT] Cancelled edit at index ${messageIndex}`);
        textDiv.innerHTML = originalTextHTML;
        userMessageEl.classList.remove('editing');
        if (actionsOutside) actionsOutside.style.display = '';
    };

    // Submit button - update and resend
    submitBtn.onclick = async () => {
        const newContent = textarea.value.trim();
        if (!newContent) {
            showNotification('Message cannot be empty');
            return;
        }

        console.log(`[EDIT] ========== SUBMIT CLICKED ==========`);
        console.log(`[EDIT] Submitting edit at messageIndex=${messageIndex}, messageId=${messageId}`);
        console.log(`[EDIT] currentRequestId=${typeof currentRequestId !== 'undefined' ? currentRequestId : 'undefined'}`);

        // === DOM STATE LOG: At submit click (BEFORE any changes) ===
        const containerBefore = document.getElementById('chatMessages');
        console.log(`[EDIT] DOM BEFORE: Container children count: ${containerBefore.children.length}`);
        Array.from(containerBefore.children).forEach((child, i) => {
            const preview = child.textContent?.substring(0, 50) || '';
            console.log(`[EDIT]   BEFORE Child ${i}: tag=${child.tagName}, class="${child.className}", data-message-id="${child.dataset?.messageId || 'none'}", text="${preview}..."`);
        });

        // IMPORTANT: Abort any existing stream FIRST to prevent old content from reappearing
        if (currentAbortController) {
            console.log(`[EDIT] Aborting existing stream before edit`);
            currentAbortController.abort();
            currentAbortController = null;
            // Also notify backend
            fetch('/api/chat/abort', { method: 'POST' }).catch(() => {});
            // Wait a moment for abort to process
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        // Reset processing state
        isProcessing = false;

        // Get fresh reference to container
        const chatContainer = document.getElementById('chatMessages');

        // Find the user message element by messageId (most reliable)
        let targetMessageEl = null;
        if (messageId) {
            targetMessageEl = chatContainer.querySelector(`[data-message-id="${messageId}"]`);
        }
        if (!targetMessageEl) {
            // Fallback to the element we captured at edit time
            targetMessageEl = userMessageEl;
        }

        if (!targetMessageEl) {
            console.error('[EDIT] Could not find target message element!');
            return;
        }

        console.log(`[EDIT] Found target message:`, targetMessageEl.className, targetMessageEl.dataset.messageId);

        // Get all children and find the index of our target message
        const allChildren = Array.from(chatContainer.children);
        const targetIndex = allChildren.indexOf(targetMessageEl);
        console.log(`[EDIT] Target is at DOM index ${targetIndex} of ${allChildren.length} children`);

        // If targetIndex is -1, the element might be nested or already removed
        // In that case, clear everything after the last message before messageIndex
        if (targetIndex === -1) {
            console.log(`[EDIT] WARNING: Target not found in children, clearing all messages from index ${messageIndex}`);
            // Clear ALL children to be safe
            chatContainer.innerHTML = '';
        } else {
            // Remove ALL elements from targetIndex onwards (inclusive)
            // This removes the edited message, its answer, and any status logs
            for (let i = allChildren.length - 1; i >= targetIndex; i--) {
                console.log(`[EDIT] Removing child ${i}: ${allChildren[i].className}`);
                allChildren[i].remove();
            }
        }

        // === DOM STATE LOG: After removal ===
        console.log(`[EDIT] ========== DOM STATE AFTER REMOVAL ==========`);
        console.log(`[EDIT] Container children count: ${chatContainer.children.length}`);
        console.log(`[EDIT] Container innerHTML length: ${chatContainer.innerHTML.length}`);
        Array.from(chatContainer.children).forEach((child, i) => {
            const preview = child.textContent?.substring(0, 50) || '';
            console.log(`[EDIT]   Child ${i}: tag=${child.tagName}, class="${child.className}", id="${child.id}", data-message-id="${child.dataset?.messageId || 'none'}", text="${preview}..."`);
        });
        const remainingMessages = chatContainer.querySelectorAll('.message');
        console.log(`[EDIT] Total .message elements: ${remainingMessages.length}`);
        console.log(`[EDIT] ================================================`);

        // Truncate chat history to remove this message and all after it
        chatHistory = chatHistory.slice(0, messageIndex);
        console.log(`[EDIT] Chat history truncated to ${chatHistory.length} messages`);

        // Save truncated history to DB and wait for completion
        await saveCurrentChatToServer(true);
        console.log(`[EDIT] DB updated with truncated history`);

        // Show welcome if empty
        if (chatHistory.length === 0 && chatContainer.children.length === 0) {
            chatContainer.innerHTML = WELCOME_HTML;
        }

        // Reset streaming state to prevent old content from reappearing
        streamingMessageDiv = null;
        streamingContent = '';
        streamingFinalized = false;
        console.log(`[EDIT] Reset streaming state before sending new message`);

        // === DOM STATE LOG: Right before sendMessage ===
        console.log(`[EDIT] ========== DOM STATE BEFORE SEND ==========`);
        const containerNow = document.getElementById('chatMessages');
        console.log(`[EDIT] Container children count: ${containerNow.children.length}`);
        Array.from(containerNow.children).forEach((child, i) => {
            const preview = child.textContent?.substring(0, 50) || '';
            console.log(`[EDIT]   Child ${i}: tag=${child.tagName}, class="${child.className}", text="${preview}..."`);
        });
        console.log(`[EDIT] ================================================`);

        // Now send the new/edited message
        const input = document.getElementById('messageInput');
        input.value = newContent;
        console.log(`[EDIT] Calling sendMessage() now...`);
        sendMessage();
    };

    // Handle Escape key to cancel
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            cancelBtn.click();
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitBtn.click();
        }
    });
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
    const successKeywords = ['command completed', 'listed', 'read', 'process completed', 'wrote', 'found'];
    // Note: 'edited' removed - we want to continue capturing code diff lines after "Edited ... with X additions"
    return successKeywords.some(kw => lower.includes(kw));
}

// Check if a line looks like a code diff line (e.g., "589 + // comment" or "590 - old code")
function isCodeDiffLine(text) {
    const trimmed = text.trim();
    // Match: number followed by + or - and then content
    return /^\d+\s*[+-]\s+/.test(trimmed);
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

    const lower = trimmed.toLowerCase();

    // Explanatory text usually starts with these words/phrases
    const explanatoryStarts = [
        'this ', 'the ', 'let me', "i'll", 'there', 'it ', 'now ',
        'would you', 'you can', 'no ', 'yes', 'i ', "i'm", 'that ',
        'here ', 'based on', 'looks like', 'appears', 'seems',
        'unfortunately', 'however', 'note:', 'note that', 'please',
        'to ', 'for ', 'if ', 'when ', 'since ', 'because ', 'as ',
        'currently', 'nothing', 'none', 'all ', 'any ', 'some '
    ];

    // Check if starts with explanatory phrase
    if (explanatoryStarts.some(s => lower.startsWith(s))) {
        return true;
    }

    // Check if it's a proper sentence (starts with capital, has spaces, no code patterns)
    const isProperSentence = /^[A-Z][a-z]/.test(trimmed) &&
                             trimmed.includes(' ') &&
                             !trimmed.includes('Error:') &&
                             !trimmed.includes('Exception:') &&
                             !trimmed.includes('.py') &&
                             !trimmed.startsWith('File ');

    return isProperSentence;
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

            // Track if this is an Edit File block with code diffs
            let inCodeDiff = false;
            let codeDiffLines = [];

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
                        // Only set inStackTrace if this looks like it will have a stack trace
                        // Simple "Command error" without traceback should end the block
                        const lower = resultContent.toLowerCase();
                        const hasTraceIndicator = lower.includes('traceback') ||
                                                  lower.includes('file "') ||
                                                  lower.includes('exception');
                        inStackTrace = hasTraceIndicator;

                        // If it's just "Command error" without trace indicators,
                        // end the block here
                        if (!hasTraceIndicator && lower === 'command error') {
                            foundEndResult = true;
                        }
                    }

                    // Check if this is an "Edited" result - expect code diff lines to follow
                    if (resultContent.toLowerCase().includes('edited') &&
                        resultContent.toLowerCase().includes('additions')) {
                        inCodeDiff = true;
                    }

                    // Only end on success keywords (not error) and not in code diff mode
                    if (isSuccessEndLine(resultContent) && !hasError && !inCodeDiff) {
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
                    // In code diff mode, empty line ends the diff section
                    if (inCodeDiff && codeDiffLines.length > 0) {
                        inCodeDiff = false;
                        break;
                    }
                    if (resultLines.length > 0 && !inStackTrace && !inCodeDiff) {
                        break;
                    }
                    i++;
                }
                // Code diff lines (e.g., "589 + // comment" or "590 - old code")
                else if (inCodeDiff && isCodeDiffLine(trimmed)) {
                    codeDiffLines.push(trimmed);
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
                // In code diff mode but not a diff line - might be explanatory text, end block
                else if (inCodeDiff) {
                    // Check if it looks like explanatory text
                    if (isExplanatoryText(trimmed)) {
                        break;
                    }
                    // Otherwise treat as continuation of diff (wrapped lines)
                    codeDiffLines.push(trimmed);
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
                codeDiff: codeDiffLines,
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
    html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}`;
    // Add copy button for Terminal blocks
    if (tool.toolType === 'terminal') {
        // Base64 encode the command to handle special characters
        const encodedCommand = btoa(unescape(encodeURIComponent(tool.command)));
        html += `<button class="tool-copy-btn" data-command="${encodedCommand}" title="Copy command"><i class="fas fa-copy"></i></button>`;
    }
    html += `</div>`;
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

    // Render code diff lines outside tool-block (after the yellow border ends)
    if (tool.codeDiff && tool.codeDiff.length > 0) {
        html += `</div>`; // Close tool-block first
        html += `<div class="tool-code-diff-wrapper">`;
        html += `<span class="diff-arrow">↳</span>`;
        html += `<div class="tool-code-diff">`;
        tool.codeDiff.forEach(line => {
            const escaped = escapeHtml(line);
            // Highlight additions (green) and removals (red)
            if (/^\d+\s*\+/.test(line)) {
                html += `<div class="diff-line diff-add">${escaped}</div>`;
            } else if (/^\d+\s*-/.test(line)) {
                html += `<div class="diff-line diff-remove">${escaped}</div>`;
            } else {
                html += `<div class="diff-line">${escaped}</div>`;
            }
        });
        html += `</div>`;
        html += `</div>`;
        return html; // Already closed tool-block
    }

    html += `</div>`;
    return html;
}

// Helper to escape HTML
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Copy tool command to clipboard
function copyToolCommand(btn) {
    const encodedCommand = btn.getAttribute('data-command');
    if (!encodedCommand) return;

    // Decode from base64
    const command = decodeURIComponent(escape(atob(encodedCommand)));

    navigator.clipboard.writeText(command).then(() => {
        // Show success feedback
        const icon = btn.querySelector('i');
        icon.className = 'fas fa-check';
        btn.classList.add('copied');
        setTimeout(() => {
            icon.className = 'fas fa-copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Add event delegation for copy and edit buttons (tool commands and user messages)
document.addEventListener('click', function(e) {
    // Tool copy button
    const toolCopyBtn = e.target.closest('.tool-copy-btn');
    if (toolCopyBtn) {
        e.preventDefault();
        e.stopPropagation();
        copyToolCommand(toolCopyBtn);
        return;
    }

    // User message copy button
    const userCopyBtn = e.target.closest('.user-copy-btn');
    if (userCopyBtn) {
        e.preventDefault();
        e.stopPropagation();
        copyUserMessage(userCopyBtn);
        return;
    }

    // User message edit button
    const editBtn = e.target.closest('.edit-btn-outside');
    if (editBtn) {
        e.preventDefault();
        e.stopPropagation();
        const encodedContent = editBtn.getAttribute('data-content');
        const index = parseInt(editBtn.getAttribute('data-index'), 10);
        const msgId = editBtn.getAttribute('data-msgid');
        if (encodedContent) {
            // Decode from base64
            const content = decodeURIComponent(escape(atob(encodedContent)));
            editMessage(editBtn, index, encodeURIComponent(content), msgId);
        }
        return;
    }
});

// Copy user message to clipboard
function copyUserMessage(btn) {
    const encodedContent = btn.getAttribute('data-content');
    if (!encodedContent) return;

    // Decode from base64
    const content = decodeURIComponent(escape(atob(encodedContent)));

    navigator.clipboard.writeText(content).then(() => {
        // Show success feedback
        const icon = btn.querySelector('i');
        icon.className = 'fas fa-check';
        btn.classList.add('copied');
        setTimeout(() => {
            icon.className = 'fas fa-copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Clean garbage characters from terminal output
function cleanGarbageCharacters(text) {
    if (!text) return '';

    // Remove trailing semicolon with numbers (e.g., ";132", ";1;2;")
    text = text.replace(/;[\d;]+\s*$/gm, '');
    text = text.replace(/;\s*$/gm, '');

    // Remove box drawing characters and related artifacts
    text = text.replace(/[╭╮╰╯│─┌┐└┘├┤┬┴┼]+\d*\s*$/gm, '');
    text = text.replace(/^[╭╮╰╯│─┌┐└┘├┤┬┴┼]+\d*\s*/gm, '');

    // Remove ANSI escape code remnants
    text = text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
    text = text.replace(/\[\d+;\d+[Hm]/g, '');

    // Remove control characters except newlines and tabs
    text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');

    // Clean up multiple consecutive blank lines
    text = text.replace(/\n{3,}/g, '\n\n');

    // Trim trailing whitespace from each line
    text = text.split('\n').map(line => line.trimEnd()).join('\n');

    return text.trim();
}

// Detect and format section headers (text ending with colon on its own line)
function formatSectionHeaders(text) {
    // Match lines that look like section headers (bold text or text ending with colon)
    // But not if they're part of a list or code block
    text = text.replace(/^(<strong>([^<]+)<\/strong>)\s*$/gm, '<div class="section-header">$1</div>');
    text = text.replace(/^([A-Z][A-Za-z\s]+):?\s*$/gm, (match, header) => {
        // Only if it looks like a section header (capitalized, not too long)
        if (header.length < 50 && !header.includes('|')) {
            return `<div class="section-header"><strong>${header}</strong></div>`;
        }
        return match;
    });
    return text;
}

// Format message with code blocks and markdown
function formatMessage(text) {
    if (!text) return '';

    // Clean garbage characters first
    text = cleanGarbageCharacters(text);

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

    // Tables - detect and convert markdown tables (improved to handle more formats)
    text = text.replace(/^(\|.+\|)\n(\|[-:\s|]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, separator, body) => {
        try {
            const headerCells = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            return `<table class="md-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table>`;
        } catch (e) {
            return match; // Return original if parsing fails
        }
    });

    // Headers
    text = text.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold and Italic
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // Section headers (standalone bold text or capitalized text before content)
    text = formatSectionHeaders(text);

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
    text = text.replace(/<p>\s*<(ul|ol|table|h[1-6]|pre|div)/g, '<$1');
    text = text.replace(/<\/(ul|ol|table|h[1-6]|pre|div)>\s*<\/p>/g, '</$1>');

    // Restore protected blocks
    toolBlocks.forEach((block, i) => { text = text.replace(`__TOOL_BLOCK_${i}__`, block); });
    codeBlocks.forEach((block, i) => { text = text.replace(`__CODE_BLOCK_${i}__`, block); });
    inlineCodes.forEach((code, i) => { text = text.replace(`__INLINE_CODE_${i}__`, code); });

    // Clean up tool blocks and section headers in paragraphs
    text = text.replace(/<p>(<div class="tool-block)/g, '$1');
    text = text.replace(/<p>(<div class="section-header)/g, '$1');
    text = text.replace(/(<\/div>)<\/p>/g, '$1');
    text = text.replace(/<br>(<div class="tool-)/g, '$1');
    text = text.replace(/<br>(<div class="section-header)/g, '$1');
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
// Refresh page
function refreshPage() {
    location.reload();
}

// Toggle settings modal
function toggleSettings() {
    const modal = document.getElementById('settingsModal');
    modal.classList.toggle('active');
    // Close dev tools if open
    document.getElementById('devToolsModal')?.classList.remove('active');
}

// Toggle developer tools modal
function toggleDevTools() {
    const modal = document.getElementById('devToolsModal');
    modal.classList.toggle('active');
    // Close settings if open
    document.getElementById('settingsModal')?.classList.remove('active');
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

// Save settings (workspace and model)
async function saveSettings() {
    console.log('[saveSettings] Called');
    const workspaceInput = document.getElementById('workspaceInput');
    const modelSelect = document.getElementById('modelSelect');
    const historyToggle = document.getElementById('historyToggle');

    const workspace = workspaceInput?.value.trim() || currentWorkspace;
    const model = modelSelect?.value || currentModel;
    const history_enabled = historyToggle?.checked ?? historyEnabled;
    console.log('[saveSettings] Saving workspace:', workspace, 'model:', model, 'history_enabled:', history_enabled);

    const url = '/api/settings';
    const requestBody = { workspace, model, history_enabled };
    logRequest('POST', url, requestBody);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        logResponse('POST', url, response.status, data);
        if (data.status === 'success') {
            currentWorkspace = data.workspace || workspace;
            currentModel = data.model || model;
            historyEnabled = data.history_enabled ?? history_enabled;
            localStorage.setItem('workspace', currentWorkspace);
            updateWorkspaceDisplay();
            updateSidebarVisibility();
            // Sync header model select
            const headerSelect = document.getElementById('modelSelectHeader');
            if (headerSelect) {
                headerSelect.value = currentModel;
            }
            showNotification('Settings saved!');
            toggleSettings();
        } else {
            showNotification('Error: ' + (data.error || 'Failed to save'));
        }
    } catch (error) {
        showNotification('Error saving settings');
    }
}

// Legacy alias for compatibility
function saveWorkspace() {
    return saveSettings();
}

// Browse workspace directories
async function browseWorkspace() {
    browserCurrentPath = currentWorkspace || '~';
    await loadBrowserDirectory(browserCurrentPath);
    document.getElementById('browserModal').classList.add('active');
}

// Load directory contents
async function loadBrowserDirectory(path) {
    const url = `/api/browse?path=${encodeURIComponent(path)}`;
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);

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

// Open logs terminal (Electron only)
async function openLogsTerminal() {
    if (window.electronAPI && window.electronAPI.openLogsTerminal) {
        try {
            const result = await window.electronAPI.openLogsTerminal();
            if (result.success) {
                showNotification(`Logs opened in ${result.terminal}`);
            } else {
                showNotification('Failed to open logs terminal: ' + (result.error || 'Unknown error'));
            }
        } catch (e) {
            showNotification('Error opening logs: ' + e.message);
        }
    } else {
        // Fallback for browser - show instructions
        showNotification('Run: journalctl --user -f | grep Flask');
    }
}

// Reset AI session
async function resetSession() {
    if (window.electronAPI && window.electronAPI.resetSession) {
        try {
            const result = await window.electronAPI.resetSession();
            if (result.success) {
                showNotification('Session reset successfully');
            } else {
                showNotification('Failed to reset session');
            }
        } catch (e) {
            showNotification('Error resetting session: ' + e.message);
        }
    } else {
        // Direct API call for browser
        try {
            const response = await fetch('/api/chat/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace: currentWorkspace })
            });
            if (response.ok) {
                showNotification('Session reset successfully');
            } else {
                showNotification('Failed to reset session');
            }
        } catch (e) {
            showNotification('Error resetting session: ' + e.message);
        }
    }
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
    const url = '/api/chats';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const chats = await response.json();
        logResponse('GET', url, response.status, { chats_count: chats.length });
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

// Create new chat
async function createNewChat() {
    try {
        // Reset the auggie session to start fresh context
        const resetUrl = '/api/session/reset';
        const resetBody = { workspace: currentWorkspace };
        logRequest('POST', resetUrl, resetBody);
        const resetResponse = await fetch(resetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(resetBody)
        });
        const resetData = await resetResponse.json();
        logResponse('POST', resetUrl, resetResponse.status, resetData);

        const createUrl = '/api/chats';
        logRequest('POST', createUrl);
        const response = await fetch(createUrl, { method: 'POST' });
        const chat = await response.json();
        logResponse('POST', createUrl, response.status, chat);

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
async function saveCurrentChatToServer(allowEmpty = false) {
    if (!currentChatId) return;
    // Allow saving empty history when explicitly requested (e.g., during edit/retry)
    if (chatHistory.length === 0 && !allowEmpty) return;

    const url = `/api/chats/${currentChatId}`;
    const requestBody = { messages: chatHistory };
    logRequest('PUT', url, { messages_count: chatHistory.length });

    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        const data = await response.json();
        logResponse('PUT', url, response.status, { messages_count: data.messages?.length });

        loadChatsFromServer();
    } catch (error) {
        console.error('[SAVE] Failed to save chat:', error);
    }
}

// Load chat from server
async function loadChatFromServer(chatId) {
    // Add cache-busting timestamp to prevent browser caching
    const url = `/api/chats/${chatId}?_t=${Date.now()}`;
    logRequest('GET', url);
    try {
        const response = await fetch(url, { cache: 'no-store' });
        const chat = await response.json();
        logResponse('GET', url, response.status, { messages_count: chat.messages?.length, error: chat.error });
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

        // Debug: log what we received from server
        console.log('[LOAD] Received from server:', chatHistory.length, 'messages');
        chatHistory.forEach((msg, i) => {
            console.log(`[LOAD]   [${i}] role=${msg.role}, content_length=${msg.content?.length || 0}, content_preview="${(msg.content || '').substring(0, 50)}..."`);
        });

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

    const url = `/api/chats/${chatId}`;
    logRequest('DELETE', url);

    try {
        const response = await fetch(url, { method: 'DELETE' });
        const data = await response.json();
        logResponse('DELETE', url, response.status, data);

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

    const url = '/api/chats/clear';
    logRequest('DELETE', url);

    try {
        const response = await fetch(url, { method: 'DELETE' });
        const data = await response.json();
        logResponse('DELETE', url, response.status, data);
        createNewChat();
        showNotification('All chats cleared');
    } catch (error) {
        console.error('Failed to clear chats:', error);
        showNotification('Failed to clear chats');
    }
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

// Close modals when clicking outside
document.addEventListener('click', function(e) {
    const settingsModal = document.getElementById('settingsModal');
    const browserModal = document.getElementById('browserModal');
    const devToolsModal = document.getElementById('devToolsModal');

    // Close settings modal if clicking outside
    if (settingsModal.classList.contains('active')) {
        const settingsContent = settingsModal.querySelector('.modal-content');
        if (!settingsContent.contains(e.target) &&
            !e.target.closest('.icon-btn[onclick*="toggleSettings"]') &&
            !e.target.closest('#workspaceBadge')) {
            settingsModal.classList.remove('active');
        }
    }

    // Close dev tools modal if clicking outside
    if (devToolsModal && devToolsModal.classList.contains('active')) {
        const devToolsContent = devToolsModal.querySelector('.modal-content');
        if (!devToolsContent.contains(e.target) &&
            !e.target.closest('.icon-btn[onclick*="toggleDevTools"]')) {
            devToolsModal.classList.remove('active');
        }
    }

    // Close browser modal if clicking outside
    if (browserModal.classList.contains('active')) {
        const browserContent = browserModal.querySelector('.modal-content');
        if (!browserContent.contains(e.target) &&
            !e.target.closest('.browse-btn')) {
            browserModal.classList.remove('active');
        }
    }
});

// ==================== REMINDERS ====================

let reminders = [];
let reminderTimers = {}; // Store setTimeout handles by reminder ID

// Day name to JS day number (0=Sunday, 1=Monday, etc.)
const DAY_TO_NUM = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
const NUM_TO_DAY = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

// Load reminders from server
async function loadReminders() {
    const url = '/api/reminders';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        reminders = data;
        renderReminders();
        scheduleAllReminders();
    } catch (error) {
        console.error('Failed to load reminders:', error);
    }
}

// Calculate ms until next trigger for a reminder
function getMsUntilNextTrigger(reminder) {
    if (!reminder.enabled) return null;

    const [hour, minute] = reminder.time.split(':').map(Number);
    const now = new Date();
    const currentDay = now.getDay();

    // Check each day starting from today
    for (let i = 0; i < 7; i++) {
        const checkDay = (currentDay + i) % 7;
        const dayName = NUM_TO_DAY[checkDay];

        if (reminder.days.includes(dayName)) {
            const triggerDate = new Date(now);
            triggerDate.setDate(now.getDate() + i);
            triggerDate.setHours(hour, minute, 0, 0);

            const msUntil = triggerDate.getTime() - now.getTime();
            if (msUntil > 0) {
                return msUntil;
            }
        }
    }
    return null;
}

// Schedule a single reminder
function scheduleReminder(reminder) {
    // Clear existing timer
    if (reminderTimers[reminder.id]) {
        clearTimeout(reminderTimers[reminder.id]);
        delete reminderTimers[reminder.id];
    }

    if (!reminder.enabled) return;

    const msUntil = getMsUntilNextTrigger(reminder);
    if (msUntil === null) return;

    console.log(`[Reminder] Scheduled "${reminder.title}" in ${Math.round(msUntil / 60000)} minutes`);

    reminderTimers[reminder.id] = setTimeout(() => {
        showDesktopNotification(reminder.title, reminder.message || 'Reminder!');
        // Reschedule for next occurrence
        scheduleReminder(reminder);
    }, msUntil);
}

// Schedule all reminders
function scheduleAllReminders() {
    // Clear all existing timers
    Object.keys(reminderTimers).forEach(id => {
        clearTimeout(reminderTimers[id]);
    });
    reminderTimers = {};

    // Schedule enabled reminders
    reminders.filter(r => r.enabled).forEach(scheduleReminder);
}

// Render reminders list
function renderReminders() {
    const list = document.getElementById('remindersList');
    if (!list) return;

    if (reminders.length === 0) {
        list.innerHTML = '<div class="no-reminders">No reminders yet</div>';
        return;
    }

    list.innerHTML = reminders.map(r => `
        <div class="reminder-item ${r.enabled ? '' : 'disabled'}" data-id="${r.id}">
            <div class="reminder-info">
                <div class="reminder-title">${escapeHtml(r.title)}</div>
                <div class="reminder-details">${r.time} • ${r.days.join(', ')}</div>
            </div>
            <div class="reminder-actions">
                <button onclick="toggleReminder('${r.id}')" title="${r.enabled ? 'Disable' : 'Enable'}">
                    <i class="fas fa-${r.enabled ? 'pause' : 'play'}"></i>
                </button>
                <button class="delete" onclick="deleteReminder('${r.id}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Add a new reminder
async function addReminder() {
    const titleInput = document.getElementById('reminderTitle');
    const messageInput = document.getElementById('reminderMessage');
    const timeInput = document.getElementById('reminderTime');
    const dayCheckboxes = document.querySelectorAll('.day-checkbox input:checked');

    const title = titleInput?.value.trim();
    if (!title) {
        showNotification('Please enter a reminder title');
        return;
    }

    const days = Array.from(dayCheckboxes).map(cb => cb.value);
    if (days.length === 0) {
        showNotification('Please select at least one day');
        return;
    }

    const url = '/api/reminders';
    const requestBody = {
        title: title,
        message: messageInput?.value.trim() || '',
        time: timeInput?.value || '09:00',
        days: days
    };
    logRequest('POST', url, requestBody);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        const data = await response.json();
        logResponse('POST', url, response.status, data);

        if (response.ok) {
            // Clear form
            titleInput.value = '';
            messageInput.value = '';
            timeInput.value = '09:00';

            await loadReminders();
            showNotification('Reminder added!');
        } else {
            showNotification('Error adding reminder');
        }
    } catch (error) {
        console.error('Failed to add reminder:', error);
        showNotification('Error adding reminder');
    }
}

// Toggle reminder enabled state
async function toggleReminder(id) {
    const url = `/api/reminders/${id}/toggle`;
    logRequest('POST', url);

    try {
        const response = await fetch(url, { method: 'POST' });
        const data = await response.json();
        logResponse('POST', url, response.status, data);

        if (response.ok) {
            await loadReminders();
        }
    } catch (error) {
        console.error('Failed to toggle reminder:', error);
    }
}

// Delete a reminder
async function deleteReminder(id) {
    const url = `/api/reminders/${id}`;
    logRequest('DELETE', url);

    try {
        const response = await fetch(url, { method: 'DELETE' });
        const data = await response.json();
        logResponse('DELETE', url, response.status, data);

        if (response.ok) {
            await loadReminders();
            showNotification('Reminder deleted');
        }
    } catch (error) {
        console.error('Failed to delete reminder:', error);
    }
}

// Show desktop notification
function showDesktopNotification(title, message) {
    // Try to use Electron notification if available
    if (window.electronAPI?.showNotification) {
        window.electronAPI.showNotification(title, message);
        return;
    }

    // Fall back to browser Notification API
    if ('Notification' in window) {
        if (Notification.permission === 'granted') {
            new Notification(title, { body: message, icon: '/static/icon.png' });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body: message, icon: '/static/icon.png' });
                }
            });
        }
    }

    // Also show in-app notification
    showNotification(`🔔 ${title}: ${message}`);
}

// Load reminders when settings modal opens
const originalToggleSettings = window.toggleSettings;
window.toggleSettings = function() {
    const modal = document.getElementById('settingsModal');
    const wasActive = modal?.classList.contains('active');

    if (typeof originalToggleSettings === 'function') {
        originalToggleSettings();
    } else {
        modal?.classList.toggle('active');
    }

    // Load reminders when opening
    if (!wasActive) {
        loadReminders();
    }
};

// Initialize reminders on page load
document.addEventListener('DOMContentLoaded', () => {
    loadReminders();

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
});
