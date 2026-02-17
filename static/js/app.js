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
let slackNotifyEnabled = false;  // Send status to Slack after completion
let slackWebhookUrl = '';  // Slack webhook URL
let statusTimerInterval = null;  // Timer for status elapsed time
let statusStartTime = null;  // When status started
let selectedImages = [];  // Array of selected image file paths

// ============ IMAGE INPUT HANDLING ============

// Handle image file selection using Electron's native dialog
async function handleImageSelect(event) {
    // Check if we're in Electron and have the API
    if (window.electronAPI && window.electronAPI.selectImages) {
        // Use Electron's native dialog for absolute paths
        try {
            const result = await window.electronAPI.selectImages();
            console.log('[IMAGES] Dialog result:', result);

            if (result.canceled || !result.images || result.images.length === 0) {
                console.log('[IMAGES] Selection canceled or empty');
                return;
            }

            for (const img of result.images) {
                console.log(`[IMAGES] Selected: ${img.path}`);

                // Avoid duplicates
                if (selectedImages.find(existing => existing.path === img.path)) {
                    console.log(`[IMAGES] Skipping duplicate: ${img.path}`);
                    continue;
                }

                selectedImages.push({
                    path: img.path,
                    name: img.name,
                    previewUrl: `file://${img.path}`  // Use file:// URL for preview
                });
            }

            updateImagePreview();
            console.log(`[IMAGES] Total selected: ${selectedImages.length}`, selectedImages.map(i => i.path));
        } catch (err) {
            console.error('[IMAGES] Error selecting images:', err);
        }
    } else {
        // Fallback for non-Electron (browser testing)
        const files = event?.target?.files;
        if (!files || files.length === 0) return;

        for (const file of files) {
            console.log(`[IMAGES] File object (fallback):`, { name: file.name, path: file.path });

            let filePath = file.path || file.name;

            if (!filePath.startsWith('/') && !filePath.startsWith('~')) {
                console.warn(`[IMAGES] Path "${filePath}" is not absolute - auggie may not find it`);
            }

            if (selectedImages.find(img => img.path === filePath)) continue;

            selectedImages.push({
                path: filePath,
                name: file.name,
                previewUrl: URL.createObjectURL(file)
            });
        }

        updateImagePreview();
        event.target.value = '';
        console.log(`[IMAGES] Selected ${selectedImages.length} images:`, selectedImages.map(i => i.path));
    }
}

// Update the image preview UI
function updateImagePreview() {
    const previewArea = document.getElementById('imagePreviewArea');
    const container = document.getElementById('imagePreviewContainer');
    const inputWrapper = document.querySelector('.chat-input-wrapper');
    const imageBtn = document.getElementById('imageBtn');

    if (selectedImages.length === 0) {
        previewArea.style.display = 'none';
        inputWrapper.classList.remove('has-images');
        imageBtn.classList.remove('has-images');
        return;
    }

    previewArea.style.display = 'flex';
    inputWrapper.classList.add('has-images');
    imageBtn.classList.add('has-images');

    container.innerHTML = selectedImages.map((img, index) => `
        <div class="image-preview-item">
            <img src="${img.previewUrl}" alt="${img.name}">
            <button class="remove-image" onclick="removeImage(${index})" title="Remove image">
                <i class="fas fa-times"></i>
            </button>
            <div class="image-name">${img.name}</div>
        </div>
    `).join('');
}

// Remove a single image by index
function removeImage(index) {
    if (index >= 0 && index < selectedImages.length) {
        // Revoke the object URL to free memory
        URL.revokeObjectURL(selectedImages[index].previewUrl);
        selectedImages.splice(index, 1);
        updateImagePreview();
        console.log(`[IMAGES] Removed image, ${selectedImages.length} remaining`);
    }
}

// Clear all selected images
function clearSelectedImages() {
    // Revoke all object URLs
    selectedImages.forEach(img => URL.revokeObjectURL(img.previewUrl));
    selectedImages = [];
    updateImagePreview();
    console.log('[IMAGES] Cleared all images');
}

// Format message for auggie with images
function formatMessageWithImages(message, images) {
    if (images.length === 0) return message;

    // Format: /images <path>|||<question>
    // Using ||| as separator because paths can contain spaces
    // Currently only supports single image (auggie limitation)
    const imagePath = images[0].path;
    return `/images ${imagePath}|||${message}`;
}

// ============ SPEECH-TO-TEXT (VOICE INPUT) using OpenAI Whisper API ============

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Toggle voice recording on/off
function toggleVoiceRecording() {
    if (isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

// Start voice recording using MediaRecorder API
async function startVoiceRecording() {
    try {
        // Request microphone access
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Create MediaRecorder
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
        });

        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            // Stop all tracks to release microphone
            stream.getTracks().forEach(track => track.stop());

            if (audioChunks.length === 0) {
                showNotification('No audio recorded', 'error');
                return;
            }

            // Create audio blob
            const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
            console.log('[VOICE] Recorded audio:', audioBlob.size, 'bytes');

            // Send to backend for transcription
            await transcribeAudio(audioBlob);
        };

        // Start recording
        mediaRecorder.start();
        isRecording = true;
        updateVoiceButtonState();
        console.log('[VOICE] Recording started');

    } catch (error) {
        console.error('[VOICE] Error starting recording:', error);

        if (error.name === 'NotAllowedError') {
            showNotification('Microphone access denied. Please allow microphone access.', 'error');
        } else if (error.name === 'NotFoundError') {
            showNotification('No microphone found. Please connect a microphone.', 'error');
        } else {
            showNotification('Error starting recording: ' + error.message, 'error');
        }
    }
}

// Stop voice recording
function stopVoiceRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        console.log('[VOICE] Recording stopped');
    }
    isRecording = false;
    updateVoiceButtonState();
}

// Send audio to backend for transcription using OpenAI Whisper API
async function transcribeAudio(audioBlob) {
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');

    // Show processing state (spinner in place of mic icon)
    voiceBtn.classList.add('processing');
    voiceIcon.classList.remove('fa-microphone');
    voiceIcon.classList.add('fa-spinner', 'fa-spin');

    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        const response = await fetch('/api/speech-to-text', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success && result.text) {
            // Insert transcribed text into input field
            const input = document.getElementById('messageInput');
            const existingText = input.value.trim();
            input.value = existingText ? existingText + ' ' + result.text : result.text;
            autoResize(input);
            input.focus();
            console.log('[VOICE] Transcribed:', result.text);
        } else {
            showNotification(result.error || 'Transcription failed', 'error');
            console.error('[VOICE] Transcription failed:', result.error);
        }

    } catch (error) {
        console.error('[VOICE] Transcription error:', error);
        showNotification('Error transcribing audio. Please try again.', 'error');
    } finally {
        // Reset button state
        voiceBtn.classList.remove('processing');
        voiceIcon.classList.remove('fa-spinner', 'fa-spin');
        voiceIcon.classList.add('fa-microphone');
    }
}

// Update voice button visual state
function updateVoiceButtonState() {
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');

    if (!voiceBtn || !voiceIcon) return;

    if (isRecording) {
        voiceBtn.classList.add('recording');
        voiceBtn.title = 'Click to stop recording';
        voiceIcon.classList.remove('fa-microphone');
        voiceIcon.classList.add('fa-microphone-slash');
    } else {
        voiceBtn.classList.remove('recording');
        voiceBtn.title = 'Voice input (Speech to Text)';
        voiceIcon.classList.remove('fa-microphone-slash');
        voiceIcon.classList.add('fa-microphone');
    }
}

// ============ BACKGROUND PROCESSING WITH MAX 2 CONCURRENT THREADS ============
const MAX_CONCURRENT_REQUESTS = 2;
const activeRequests = new Map();  // chatId -> { abortController, streamingContent, status, chatHistory, requestId }

// Get count of active requests
function getActiveRequestCount() {
    return activeRequests.size;
}

// Check if a chat has an active request
function hasActiveRequest(chatId) {
    return activeRequests.has(chatId);
}

// Get active request for a chat
function getActiveRequest(chatId) {
    return activeRequests.get(chatId);
}

// Create a new active request entry
function createActiveRequest(chatId, abortController, requestId) {
    const request = {
        abortController,
        requestId,
        streamingContent: '',
        status: 'starting',
        statusMessage: '',
        chatHistory: [...chatHistory],  // Copy current history
        startTime: Date.now()
    };
    activeRequests.set(chatId, request);
    console.log(`[BG] Created request for chat ${chatId}, active count: ${activeRequests.size}`);
    updateBackgroundIndicator();
    return request;
}

// Update streaming content for a background request
function updateActiveRequestContent(chatId, content) {
    const request = activeRequests.get(chatId);
    if (request) {
        request.streamingContent = content;
    }
}

// Update status for a background request
function updateActiveRequestStatus(chatId, status, message = '') {
    const request = activeRequests.get(chatId);
    if (request) {
        request.status = status;
        request.statusMessage = message;
    }
}

// Complete and remove an active request
// For background requests: adds message to history and saves
// For foreground requests: just cleans up tracking (finalizeStreamingMessage handles the rest)
function completeActiveRequest(chatId, finalContent, isBackground = false) {
    const request = activeRequests.get(chatId);
    if (request) {
        console.log(`[BG] Completing request for chat ${chatId}, isBackground: ${isBackground}, content length: ${finalContent?.length}`);

        // Only add to history for background requests
        // Foreground requests are handled by finalizeStreamingMessage
        if (isBackground) {
            const index = request.chatHistory.length;
            const messageId = generateMessageId(chatId, index, finalContent);
            request.chatHistory.push({ role: 'assistant', content: finalContent, messageId });

            // Save to cache and server
            saveChatToCache(chatId, request.chatHistory);
            fetch(`/api/chats/${chatId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: request.chatHistory })
            }).then(() => markCacheSynced(chatId))
              .catch(err => console.error('[BG] Failed to save completed chat:', err));
        }

        activeRequests.delete(chatId);
        updateBackgroundIndicator();

        // Refresh sidebar to update indicators
        loadChatsFromServer();
    }
}

// Abort and remove an active request
function abortActiveRequest(chatId) {
    const request = activeRequests.get(chatId);
    if (request) {
        console.log(`[BG] Aborting request for chat ${chatId}`);
        request.abortController.abort();
        activeRequests.delete(chatId);
        updateBackgroundIndicator();
    }
}

// ============ PENDING STREAM POLLING ============
// When user refreshes during streaming, poll server for updates
let pendingStreamPolls = new Map();  // chatId -> intervalId

function startPendingStreamPoll(chatId) {
    // Don't start multiple polls for the same chat
    if (pendingStreamPolls.has(chatId)) {
        console.log('[POLL] Already polling for chat:', chatId);
        return;
    }

    console.log('[POLL] Starting poll for pending stream:', chatId);

    // Show a reconnecting indicator
    showTypingIndicator('Reconnecting to stream...');
    isProcessing = true;
    document.getElementById('sendBtn').disabled = true;
    document.getElementById('messageInput').disabled = true;
    showStopButton();

    let pollCount = 0;
    const maxPolls = 120;  // Max 2 minutes of polling (1 second intervals)

    const pollInterval = setInterval(async () => {
        pollCount++;

        // Stop if we've exceeded max polls
        if (pollCount > maxPolls) {
            console.log('[POLL] Max polls reached, stopping');
            stopPendingStreamPoll(chatId);
            hideTypingIndicator();
            isProcessing = false;
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('messageInput').disabled = false;
            hideStopButton();
            return;
        }

        try {
            const response = await fetch(`/api/chats/${chatId}?_t=${Date.now()}`, { cache: 'no-store' });
            const chat = await response.json();

            if (chat.error) {
                console.log('[POLL] Chat not found, stopping poll');
                stopPendingStreamPoll(chatId);
                return;
            }

            // Update chat history with latest from server
            const newMessages = chat.messages || [];
            if (newMessages.length > chatHistory.length) {
                console.log('[POLL] Got new messages:', newMessages.length - chatHistory.length);
                chatHistory = newMessages;
                renderChatMessages(chatHistory);
            }

            // Check if streaming is complete
            if (!chat.streaming_status || chat.streaming_status === null) {
                console.log('[POLL] Streaming complete, stopping poll');
                stopPendingStreamPoll(chatId);
                hideTypingIndicator();
                isProcessing = false;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('messageInput').disabled = false;
                hideStopButton();

                // Final render with complete messages
                chatHistory = chat.messages || [];
                renderChatMessages(chatHistory);
                saveChatToCache(chatId, chatHistory);
                loadChatsFromServer();
            } else if (chat.streaming_status === 'pending' && pollCount > 3) {
                // Pending for too long - backend stopped but didn't clean up
                // Show partial content and let user know
                console.log('[POLL] Pending timeout - showing partial content');
                stopPendingStreamPoll(chatId);
                hideTypingIndicator();
                isProcessing = false;
                document.getElementById('sendBtn').disabled = false;
                document.getElementById('messageInput').disabled = false;
                hideStopButton();

                // Render what we have
                chatHistory = chat.messages || [];
                renderChatMessages(chatHistory);

                // Check if we have partial content (answer was interrupted mid-stream)
                const lastMsg = chatHistory.length > 0 ? chatHistory[chatHistory.length - 1] : null;
                const hasPartialAnswer = lastMsg && lastMsg.role === 'assistant' && lastMsg.partial === true;
                const hasAnswer = chatHistory.some(m => m.role === 'assistant');

                if (!hasAnswer) {
                    // No answer at all - show full interrupted message
                    addMessage('assistant', '⚠️ Response was interrupted. Please try asking again.', true);
                } else if (hasPartialAnswer) {
                    // Has partial answer - append interrupted note to existing message
                    const assistantMsgs = document.querySelectorAll('.message.assistant');
                    if (assistantMsgs.length > 0) {
                        const lastAssistantMsg = assistantMsgs[assistantMsgs.length - 1];
                        const contentDiv = lastAssistantMsg.querySelector('.content');
                        if (contentDiv && !contentDiv.innerHTML.includes('interrupted')) {
                            contentDiv.innerHTML += '<p class="interrupted-note" style="color: var(--warning-color); margin-top: 1em; font-style: italic;">⚠️ Response was interrupted</p>';
                        }
                    }
                }

                // Clear the pending status on server
                fetch(`/api/chats/${chatId}/clear-streaming`, { method: 'POST' }).catch(() => {});
                loadChatsFromServer();
            } else {
                // Still streaming, update status
                updateTypingIndicatorText(`Waiting for response... (${pollCount}s)`);
            }
        } catch (error) {
            console.error('[POLL] Error polling:', error);
        }
    }, 1000);

    pendingStreamPolls.set(chatId, pollInterval);
}

function stopPendingStreamPoll(chatId) {
    const intervalId = pendingStreamPolls.get(chatId);
    if (intervalId) {
        clearInterval(intervalId);
        pendingStreamPolls.delete(chatId);
        console.log('[POLL] Stopped poll for chat:', chatId);
    }
}

function updateTypingIndicatorText(text) {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        const textSpan = indicator.querySelector('span');
        if (textSpan) {
            textSpan.textContent = text;
        }
    }
}

// Update the background processing indicator in UI
function updateBackgroundIndicator() {
    let indicator = document.getElementById('backgroundIndicator');
    const count = activeRequests.size;

    if (count === 0) {
        if (indicator) indicator.style.display = 'none';
        return;
    }

    // Create indicator if it doesn't exist
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'backgroundIndicator';
        indicator.className = 'background-indicator';
        indicator.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span>0</span> background`;
        document.body.appendChild(indicator);
    }

    indicator.style.display = 'flex';
    indicator.querySelector('span').textContent = count;
    indicator.title = `${count} request(s) processing in background`;
}
// ============ END BACKGROUND PROCESSING ============

// ============ LOCAL CACHE MECHANISM FOR MESSAGE RELIABILITY ============
const CACHE_PREFIX = 'chat_cache_';
const CACHE_META_KEY = 'chat_cache_meta';
let cacheAutoSaveInterval = null;

// Save chat to local cache immediately
function saveChatToCache(chatId, messages, streamingContent = '') {
    if (!chatId) return;
    try {
        const cacheData = {
            messages: messages,
            streamingContent: streamingContent,
            timestamp: Date.now(),
            synced: false
        };
        localStorage.setItem(CACHE_PREFIX + chatId, JSON.stringify(cacheData));
        console.log('[CACHE] Saved chat to cache:', chatId, 'messages:', messages.length);

        // Update cache meta (list of cached chats)
        updateCacheMeta(chatId);
    } catch (e) {
        console.error('[CACHE] Failed to save to cache:', e);
    }
}

// Load chat from local cache
function loadChatFromCache(chatId) {
    if (!chatId) return null;
    try {
        const cached = localStorage.getItem(CACHE_PREFIX + chatId);
        if (cached) {
            const data = JSON.parse(cached);
            console.log('[CACHE] Loaded chat from cache:', chatId, 'messages:', data.messages?.length);
            return data;
        }
    } catch (e) {
        console.error('[CACHE] Failed to load from cache:', e);
    }
    return null;
}

// Mark cache as synced with server
function markCacheSynced(chatId) {
    if (!chatId) return;
    try {
        const cached = localStorage.getItem(CACHE_PREFIX + chatId);
        if (cached) {
            const data = JSON.parse(cached);
            data.synced = true;
            data.syncedAt = Date.now();
            localStorage.setItem(CACHE_PREFIX + chatId, JSON.stringify(data));
        }
    } catch (e) {
        console.error('[CACHE] Failed to mark synced:', e);
    }
}

// Update cache metadata (track which chats are cached)
function updateCacheMeta(chatId) {
    try {
        let meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        meta[chatId] = Date.now();

        // Clean up old cache entries (keep last 50 chats)
        const chatIds = Object.keys(meta).sort((a, b) => meta[b] - meta[a]);
        if (chatIds.length > 50) {
            chatIds.slice(50).forEach(id => {
                delete meta[id];
                localStorage.removeItem(CACHE_PREFIX + id);
            });
        }

        localStorage.setItem(CACHE_META_KEY, JSON.stringify(meta));
    } catch (e) {
        console.error('[CACHE] Failed to update meta:', e);
    }
}

// Get unsynced chats from cache
function getUnsyncedChats() {
    const unsynced = [];
    try {
        const meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        Object.keys(meta).forEach(chatId => {
            const cached = localStorage.getItem(CACHE_PREFIX + chatId);
            if (cached) {
                const data = JSON.parse(cached);
                if (!data.synced && data.messages?.length > 0) {
                    unsynced.push({ chatId, ...data });
                }
            }
        });
    } catch (e) {
        console.error('[CACHE] Failed to get unsynced:', e);
    }
    return unsynced;
}

// Sync unsynced chats to server
async function syncUnsyncedChats() {
    const unsynced = getUnsyncedChats();
    if (unsynced.length === 0) return;

    console.log('[CACHE] Syncing', unsynced.length, 'unsynced chats to server');
    for (const chat of unsynced) {
        try {
            const response = await fetch(`/api/chats/${chat.chatId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: chat.messages })
            });
            if (response.ok) {
                markCacheSynced(chat.chatId);
                console.log('[CACHE] Synced chat:', chat.chatId);
            }
        } catch (e) {
            console.error('[CACHE] Failed to sync chat:', chat.chatId, e);
        }
    }
}

// Start auto-save interval for streaming content
function startCacheAutoSave() {
    if (cacheAutoSaveInterval) return;
    cacheAutoSaveInterval = setInterval(() => {
        if (currentChatId && (chatHistory.length > 0 || streamingContent)) {
            saveChatToCache(currentChatId, chatHistory, streamingContent);
        }
    }, 3000); // Save every 3 seconds during activity
    console.log('[CACHE] Auto-save started');
}

// Stop auto-save interval
function stopCacheAutoSave() {
    if (cacheAutoSaveInterval) {
        clearInterval(cacheAutoSaveInterval);
        cacheAutoSaveInterval = null;
        console.log('[CACHE] Auto-save stopped');
    }
}

// Clear cache for a specific chat
function clearChatCache(chatId) {
    try {
        localStorage.removeItem(CACHE_PREFIX + chatId);
        let meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        delete meta[chatId];
        localStorage.setItem(CACHE_META_KEY, JSON.stringify(meta));
    } catch (e) {
        console.error('[CACHE] Failed to clear cache:', e);
    }
}
// ============ END LOCAL CACHE MECHANISM ============

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
        <h2>Hello, what do you want?</h2>
        <div class="quick-actions">
            <button class="action-btn" onclick="sendSuggestion('Show me the folder structure of this project with main files and their purposes')">
                <i class="fas fa-sitemap"></i>
                <span>Project structure</span>
            </button>
            <button class="action-btn" onclick="sendSuggestion('List all files in the current directory and briefly describe what each one does')">
                <i class="fas fa-folder-tree"></i>
                <span>List files</span>
            </button>
            <button class="action-btn" onclick="sendSuggestion('Check if any application is running on port 5000 and show me the process details')">
                <i class="fas fa-server"></i>
                <span>Check port</span>
            </button>
            <button class="action-btn" onclick="sendSuggestion('What are the latest AI news and developments today?')">
                <i class="fas fa-newspaper"></i>
                <span>AI news today</span>
            </button>
            <button class="action-btn" onclick="sendSuggestion('Find all TODO comments in this project and list them with their file locations')">
                <i class="fas fa-clipboard-list"></i>
                <span>Find TODOs</span>
            </button>
            <button class="action-btn" onclick="sendSuggestion('Show me the git status and recent commits in this repository')">
                <i class="fas fa-code-branch"></i>
                <span>Git status</span>
            </button>
        </div>
    </div>
`;

// Initialize the app
// Render chat messages in the container
function renderChatMessages(messages) {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';

    if (!messages || messages.length === 0) {
        container.innerHTML = WELCOME_HTML;
        return;
    }

    messages.forEach((msg, idx) => {
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

// Wait for server to be ready with retry
async function waitForServer(maxRetries = 5, delayMs = 500) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            const response = await fetch('/api/chats', { cache: 'no-store' });
            if (response.ok) {
                const chats = await response.json();
                console.log(`[INIT] Server ready after ${i + 1} attempt(s), found ${chats.length} chats`);
                return chats;
            }
        } catch (e) {
            console.log(`[INIT] Server not ready, attempt ${i + 1}/${maxRetries}...`);
        }
        await new Promise(resolve => setTimeout(resolve, delayMs));
    }
    console.log('[INIT] Server not responding after retries');
    return null;
}

document.addEventListener('DOMContentLoaded', async () => {
    // Apply cached settings immediately for instant UI
    loadSettings();
    checkAuthStatus();

    // Restore sidebar state
    const savedSidebarState = localStorage.getItem('sidebarOpen');
    if (savedSidebarState === 'false') {
        toggleSidebar();
    }

    // Render cached chat list immediately (instant UI)
    const cachedChats = loadCachedChatList();
    if (cachedChats && cachedChats.length > 0) {
        console.log('[INIT] Rendering cached chat list:', cachedChats.length, 'chats');
        renderChatHistory(cachedChats);
    }

    // Render cached messages for saved chat immediately
    const savedChatId = localStorage.getItem('currentChatId');
    const chatMessagesContainer = document.getElementById('chatMessages');
    if (savedChatId) {
        const cachedData = loadChatFromCache(savedChatId);
        if (cachedData && cachedData.messages && cachedData.messages.length > 0) {
            console.log('[INIT] Rendering cached messages for:', savedChatId);
            currentChatId = savedChatId;
            chatHistory = cachedData.messages;
            renderChatMessages(chatHistory);
        }
    }
    // Make container visible after rendering correct content
    if (chatMessagesContainer) {
        chatMessagesContainer.style.visibility = 'visible';
    }

    // Start cache auto-save for reliability
    startCacheAutoSave();

    // Sync any unsynced chats from previous sessions
    syncUnsyncedChats();

    // Load settings and chats from server in background
    const [settingsResult, chats] = await Promise.all([
        loadSettingsFromServer().catch(e => { console.log('[INIT] Settings load failed:', e); return null; }),
        waitForServer()
    ]);

    if (chats === null) {
        // Server not responding - we already rendered from cache above
        if (!currentChatId) {
            showNotification('Server not responding. Please restart the app.');
        }
        return;
    }

    // Update chat history from server (may have newer data)
    renderChatHistory(chats);
    const chatIds = chats.map(c => c.id);
    console.log('[INIT] Server returned chat IDs:', chatIds);

    // If we already loaded a cached chat, verify it still exists on server
    if (currentChatId && chatIds.includes(currentChatId)) {
        // Chat exists, refresh from server in background
        console.log('[INIT] Refreshing current chat from server:', currentChatId);
        loadChatFromServer(currentChatId);
    } else if (savedChatId && chatIds.includes(savedChatId)) {
        // Saved chat exists, load it
        console.log('[INIT] Loading saved chat:', savedChatId);
        await loadChatFromServer(savedChatId);
    } else if (chatIds.length > 0) {
        // Saved chat doesn't exist but there are other chats - load the most recent one
        console.log('[INIT] Saved chat not found, loading most recent chat:', chatIds[0]);
        await loadChatFromServer(chatIds[0]);
    } else {
        // No chats exist - create a new chat
        console.log('[INIT] No chats exist, creating new chat');
        await createNewChat();
    }
    console.log('[INIT] After restore, currentChatId:', currentChatId);
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
            localStorage.setItem('workspace', currentWorkspace);
            updateWorkspaceDisplay();
        }
        if (data.model) {
            currentModel = data.model;
            localStorage.setItem('currentModel', currentModel);
        }
        if (data.available_models) {
            availableModels = data.available_models;
            localStorage.setItem('availableModels', JSON.stringify(availableModels));
            populateModelSelect();
        }
        // Handle history_enabled setting
        if (typeof data.history_enabled !== 'undefined') {
            historyEnabled = data.history_enabled;
            updateHistoryToggle();
            updateSidebarVisibility();
        }
        // Handle slack settings
        if (typeof data.slack_notify !== 'undefined') {
            slackNotifyEnabled = data.slack_notify;
            slackWebhookUrl = data.slack_webhook_url || '';
            updateSlackToggle();
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

// Update Slack toggle checkbox state
function updateSlackToggle() {
    const toggle = document.getElementById('slackNotifyToggle');
    const webhookSetting = document.getElementById('slackWebhookSetting');
    const webhookInput = document.getElementById('slackWebhookUrl');

    if (toggle) {
        toggle.checked = slackNotifyEnabled;
        // Show/hide webhook URL field based on toggle
        if (webhookSetting) {
            webhookSetting.style.display = slackNotifyEnabled ? 'flex' : 'none';
        }
        if (webhookInput) {
            webhookInput.value = slackWebhookUrl;
        }

        // Add change listener for toggle
        toggle.onchange = async function() {
            slackNotifyEnabled = this.checked;
            if (webhookSetting) {
                webhookSetting.style.display = slackNotifyEnabled ? 'flex' : 'none';
            }
            // Save to server
            await saveSlackSettings();
            showNotification(slackNotifyEnabled ? 'Slack notifications enabled' : 'Slack notifications disabled');
        };
    }

    // Add change listener for webhook URL
    if (webhookInput) {
        webhookInput.onblur = async function() {
            if (slackWebhookUrl !== this.value) {
                slackWebhookUrl = this.value;
                await saveSlackSettings();
                if (slackWebhookUrl) {
                    showNotification('Slack webhook URL saved');
                }
            }
        };
    }
}

// Save Slack settings to server
async function saveSlackSettings() {
    const url = '/api/settings';
    const requestBody = {
        slack_notify: slackNotifyEnabled,
        slack_webhook_url: slackWebhookUrl
    };
    try {
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        console.log('[slackSettings] Updated:', requestBody);
    } catch (error) {
        console.error('Failed to update Slack settings:', error);
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

    // Check max concurrent requests limit
    if (getActiveRequestCount() >= MAX_CONCURRENT_REQUESTS) {
        showNotification(`Maximum ${MAX_CONCURRENT_REQUESTS} concurrent requests reached. Please wait for one to complete.`);
        return;
    }

    // Create a chat first if we don't have one
    if (!currentChatId) {
        console.log('[API] No current chat, creating one first...');
        try {
            const createUrl = '/api/chats';
            const createResponse = await fetch(createUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace: currentWorkspace })
            });
            const newChat = await createResponse.json();
            currentChatId = newChat.id;
            localStorage.setItem('currentChatId', currentChatId);
            console.log('[API] Created new chat:', currentChatId);
            // Refresh sidebar to show new chat
            loadChatsFromServer();
        } catch (error) {
            console.error('[API] Failed to create chat:', error);
            showNotification('Failed to create chat. Please try again.');
            return;
        }
    }

    // Increment request ID - this invalidates any previous request
    currentRequestId++;
    const thisRequestId = currentRequestId;
    const thisChatId = currentChatId;  // Capture chat ID for this request
    console.log(`[API] Starting request #${thisRequestId} for chat ${thisChatId}`);

    // Capture selected images before clearing
    const imagesToSend = [...selectedImages];
    const hasImages = imagesToSend.length > 0;

    // Format message for auggie if images are attached
    const formattedMessage = formatMessageWithImages(message, imagesToSend);

    // Display message to user (show original message, not the /images command)
    const displayMessage = hasImages
        ? `📷 [${imagesToSend.length} image${imagesToSend.length > 1 ? 's' : ''}] ${message}`
        : message;

    input.value = '';
    autoResize(input);
    clearSelectedImages();  // Clear images after capturing
    hideWelcome();
    addMessage('user', displayMessage, true);  // skipSave: backend handles saving
    showTypingIndicator('Connecting...');
    isProcessing = true;
    document.getElementById('sendBtn').disabled = true;
    showStopButton();

    // Create abort controller for this request
    currentAbortController = new AbortController();

    // Register this as an active background request
    const activeRequest = createActiveRequest(thisChatId, currentAbortController, thisRequestId);

    const url = '/api/chat/stream';
    // Send the formatted message (with /images prefix if images attached)
    const requestBody = { message: formattedMessage, workspace: currentWorkspace, chatId: currentChatId };
    logRequest('POST', url, requestBody);

    if (hasImages) {
        console.log(`[IMAGES] Sending message with ${imagesToSend.length} images:`, imagesToSend.map(i => i.path));
    }

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
                // Check if user switched to different chat (background processing)
                const isBackground = thisChatId !== currentChatId;
                const bgRequest = getActiveRequest(thisChatId);

                try {
                    const data = JSON.parse(line.slice(6));
                    eventCount++;

                    switch (data.type) {
                        case 'status':
                            // Update background request status tracking
                            if (bgRequest) {
                                updateActiveRequestStatus(thisChatId, 'processing', data.message);
                            }
                            // Only update UI if this is foreground (current chat)
                            if (!isBackground) {
                                updateTypingStatus(data.message);
                            }
                            break;
                        case 'stream_start':
                            console.log(`[API] Request #${thisRequestId} stream_start (background: ${isBackground})`);
                            if (bgRequest) {
                                updateActiveRequestStatus(thisChatId, 'streaming');
                            }
                            // Only create streaming div if this is foreground
                            if (!isBackground) {
                                startStreamingMessage(thisRequestId);
                            }
                            break;
                        case 'stream':
                            // Always accumulate content for the active request tracking
                            if (bgRequest) {
                                bgRequest.streamingContent += data.content;
                            }
                            // Update UI if this is the current (foreground) chat
                            if (!isBackground) {
                                appendStreamingContent(data.content, thisRequestId);
                            }
                            break;
                        case 'stream_end':
                            console.log(`[API] Request #${thisRequestId} stream_end (background: ${isBackground})`);
                            // Get final content - prefer accumulated streamingContent over backend's
                            const bgContent = bgRequest?.streamingContent || '';
                            const backendContent = data.content?.trim() || '';
                            // For foreground, use global streamingContent; for background use bgRequest's
                            const streamedContent = isBackground ? bgContent : (streamingContent?.trim() || '');
                            const useStreamed = streamedContent.length >= backendContent.length;
                            const finalContent = useStreamed ? (isBackground ? bgContent : streamingContent) : (backendContent || streamedContent);
                            console.log(`[API] Using ${useStreamed ? 'STREAMED' : 'BACKEND'} content, length:`, finalContent?.length);

                            if (isBackground) {
                                // Complete background request - save to that chat
                                completeActiveRequest(thisChatId, finalContent, true);
                            } else {
                                // Foreground - finalize UI and complete tracking
                                finalizeStreamingMessage(finalContent, thisRequestId);
                                completeActiveRequest(thisChatId, finalContent, false);
                                hideTypingIndicator();
                            }
                            streamingCompleted = true;
                            break;
                        case 'response':
                            console.log('[API] response - length:', data.message?.length, 'streamingCompleted:', streamingCompleted);
                            if (!streamingCompleted) {
                                if (isBackground) {
                                    // Complete background request
                                    completeActiveRequest(thisChatId, data.message, true);
                                } else {
                                    console.log('[API] Adding response via addMessage (streaming was not used)');
                                    hideTypingIndicator();
                                    addMessage('assistant', data.message);
                                    completeActiveRequest(thisChatId, data.message, false);
                                }
                            }
                            if (data.workspace && data.workspace !== currentWorkspace) {
                                currentWorkspace = data.workspace;
                                updateWorkspaceDisplay();
                            }
                            break;
                        case 'error':
                            // Remove from active requests on error
                            activeRequests.delete(thisChatId);
                            updateBackgroundIndicator();
                            if (!isBackground) {
                                hideTypingIndicator();
                                // Don't save error messages to database - use skipSave=true
                                addMessage('assistant', `❌ Error: ${data.message}`, true);
                            }
                            break;
                        case 'aborted':
                            // Request was aborted (e.g., due to edit/retry)
                            console.log('[API] Request aborted by server');
                            activeRequests.delete(thisChatId);
                            updateBackgroundIndicator();
                            if (!isBackground) {
                                hideTypingIndicator();
                                if (streamingMessageDiv) {
                                    streamingMessageDiv.remove();
                                    streamingMessageDiv = null;
                                }
                                streamingContent = '';
                                streamingFinalized = true;
                            }
                            break;
                        case 'done':
                            // Response complete
                            console.log(`[API] done event received (background: ${isBackground})`);

                            // Ensure request is completed and cleaned up
                            if (!streamingCompleted && bgRequest) {
                                const doneContent = bgRequest.streamingContent || streamingContent;
                                if (isBackground) {
                                    completeActiveRequest(thisChatId, doneContent, true);
                                } else if (streamingMessageDiv) {
                                    finalizeStreamingMessage(doneContent, thisRequestId);
                                    completeActiveRequest(thisChatId, doneContent, false);
                                }
                                streamingCompleted = true;
                            }

                            // Only update UI if this is current chat
                            if (!isBackground && thisChatId === currentChatId) {
                                isProcessing = false;
                                hideTypingIndicator();
                                const sendBtnDone = document.getElementById('sendBtn');
                                const inputDone = document.getElementById('messageInput');
                                if (sendBtnDone) {
                                    sendBtnDone.disabled = false;
                                }
                                if (inputDone) {
                                    inputDone.disabled = false;
                                    inputDone.readOnly = false;
                                    inputDone.style.pointerEvents = 'auto';
                                    inputDone.focus();
                                }
                                hideStopButton();
                            }
                            console.log('[API] Done processing complete');
                            break;
                    }
                } catch (e) { /* ignore parse errors */ }
            }
        }
    } catch (error) {
        // Clean up active request on error
        activeRequests.delete(thisChatId);
        updateBackgroundIndicator();

        if (error.name === 'AbortError') {
            console.log(`[API] Request #${thisRequestId} aborted by user`);
            // Only cleanup UI if this is the current chat
            if (thisChatId === currentChatId) {
                hideTypingIndicator();
                if (streamingMessageDiv) {
                    console.log('[API] Removing partial streaming message due to abort');
                    streamingMessageDiv.remove();
                    streamingMessageDiv = null;
                    streamingContent = '';
                    streamingFinalized = true;
                }
            }
        } else {
            console.error('Error:', error);
            if (thisChatId === currentChatId) {
                hideTypingIndicator();
                // Don't save error messages to database - use skipSave=true
                addMessage('assistant', '❌ Connection error. Make sure the server is running.', true);
            }
        }
    } finally {
        console.log(`[API] Request #${thisRequestId} finally block for chat ${thisChatId}`);

        const isBackgroundFinal = thisChatId !== currentChatId;

        // Only do UI cleanup if this is the current chat
        if (isBackgroundFinal) {
            console.log(`[API] Request was for background chat ${thisChatId}, skipping UI cleanup`);
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
        // User messages: plain text with newlines preserved, no markdown formatting
        const plainContent = escapeHtml(content).replace(/\n/g, '<br>');
        return `<div class="message-avatar"><i class="fas ${icon}"></i></div>
            <div class="message-content">
                <div class="message-text">${plainContent}</div>
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

    // Don't overwrite status here - let backend's dynamic status messages show
    // (e.g., "Summarizing conversation...", "Executing tool...", etc.)

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

// ============================================================================
// TOOL FORMATTING CONFIG - Edit this section when changing AI providers
// ============================================================================
const TOOL_CONFIG = {
    // Tools: name, icon, type (for styling)
    tools: [
        { name: 'Terminal', icon: 'fa-terminal', type: 'terminal' },
        { name: 'Read Directory', icon: 'fa-folder-open', type: 'read' },
        { name: 'Read directory', icon: 'fa-folder-open', type: 'read' },
        { name: 'Read File', icon: 'fa-file-code', type: 'read' },
        { name: 'Read file', icon: 'fa-file-code', type: 'read' },
        { name: 'Read Process', icon: 'fa-stream', type: 'read' },
        { name: 'Write File', icon: 'fa-file-pen', type: 'action' },
        { name: 'Edit File', icon: 'fa-edit', type: 'action' },
        { name: 'Search', icon: 'fa-search', type: 'action' },
        { name: 'Codebase Search', icon: 'fa-code', type: 'action' },
        { name: 'Codebase search', icon: 'fa-code', type: 'action' },
        { name: 'Web Search', icon: 'fa-globe', type: 'action' },
        { name: 'Add Tasks', icon: 'fa-list-check', type: 'task' },
        { name: 'Update Tasks', icon: 'fa-tasks', type: 'task' },
    ],
    // Result line prefix
    resultPrefix: '↳',
    // Result status keywords that END a tool block (case insensitive)
    resultEndKeywords: [
        'command completed', 'command error', 'listed', 'read',
        'process completed', 'wrote', 'edited', 'found', 'no results',
        'added tasks successfully', 'updated tasks'
    ],
};

// Cached regex for tool parsing - built once for performance
let _cachedToolStartRegex = null;
let _cachedToolEndRegex = null;  // For reversed pattern: "filename - read file"
function getToolStartRegex() {
    if (!_cachedToolStartRegex) {
        const toolNames = TOOL_CONFIG.tools.map(t => t.name).join('|');
        _cachedToolStartRegex = new RegExp(`^(${toolNames})\\s+-\\s+(.+)$`, 'i');
    }
    return _cachedToolStartRegex;
}

// Get regex for reversed pattern: "content - tool name" (e.g., "package.json - read file")
function getToolEndRegex() {
    if (!_cachedToolEndRegex) {
        const toolNames = TOOL_CONFIG.tools.map(t => t.name).join('|');
        _cachedToolEndRegex = new RegExp(`^(.+?)\\s+-\\s+(${toolNames})$`, 'i');
    }
    return _cachedToolEndRegex;
}

// Match a line against tool patterns (both "Tool - content" and "content - tool")
function matchToolLine(line) {
    // Try standard pattern first: "Read File - package.json"
    const startRegex = getToolStartRegex();
    let match = line.match(startRegex);
    if (match) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === match[1].toLowerCase());
        if (toolConfig) {
            return { toolConfig, content: match[2] };
        }
    }

    // Try reversed pattern: "package.json - read file"
    const endRegex = getToolEndRegex();
    match = line.match(endRegex);
    if (match) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === match[2].toLowerCase());
        if (toolConfig) {
            return { toolConfig, content: match[1] };
        }
    }

    // Try line range pattern: "path/file.js - lines 345-420" (Read file with range)
    const lineRangeMatch = line.match(/^(.+?)\s+-\s+lines\s+(\d+)-(\d+)$/i);
    if (lineRangeMatch) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === 'read file');
        if (toolConfig) {
            const filePath = lineRangeMatch[1];
            const startLine = lineRangeMatch[2];
            const endLine = lineRangeMatch[3];
            return { toolConfig, content: filePath, lineRange: { start: startLine, end: endLine } };
        }
    }

    // Try read filesearch pattern: "path/file.py - read filesearch: searchQuery"
    const fileSearchMatch = line.match(/^(.+?)\s+-\s+read\s+filesearch:\s*(.+)$/i);
    if (fileSearchMatch) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === 'read file');
        if (toolConfig) {
            const filePath = fileSearchMatch[1];
            const searchQuery = fileSearchMatch[2];
            return { toolConfig, content: filePath, searchQuery: searchQuery };
        }
    }

    return null;
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

    // Handle streaming tool blocks
    const toolBlocks = [];
    result = formatStreamingToolBlocks(result, toolBlocks);

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
            // Split and keep empty cells (slice removes leading/trailing empty from | split)
            const headerParts = header.split('|').slice(1, -1);
            const headerCells = headerParts.map(c => `<th>${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cellParts = row.split('|').slice(1, -1);
                const cells = cellParts.map(c => `<td>${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            // Encode original markdown for copy
            const encodedTable = btoa(unescape(encodeURIComponent(match.trim())));
            return `<div class="table-wrapper"><button class="table-copy-btn" data-table="${encodedTable}" title="Copy table"><i class="fas fa-copy"></i></button><table class="md-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
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

    // Section headers (text ending with colon like "Summary:", "Key findings:")
    result = result.replace(/^([A-Z][A-Za-z0-9\s\-]+):\s*$/gm, (match, header) => {
        if (header.length < 60 && !header.includes('|')) {
            return `<div class="section-header"><strong>${header}</strong></div>`;
        }
        return match;
    });

    // Simple list handling - convert existing markdown lists
    result = result.replace(/^[\s]*[-•]\s+(.+)$/gm, '<li class="stream-li">$1</li>');
    result = result.replace(/^[\s]*(\d+)\.\s+(.+)$/gm, '<li class="stream-li-num">$1. $2</li>');

    // Process lines for formatting
    const lines = result.split('\n');
    let prevWasEmpty = true;
    const formattedLines = lines.map((line, idx) => {
        const trimmed = line.trim();

        // Skip empty lines
        if (!trimmed) {
            prevWasEmpty = true;
            return line;
        }

        // Skip already formatted elements
        if (trimmed.startsWith('<h') ||
            trimmed.startsWith('<li') ||
            trimmed.startsWith('<div') ||
            trimmed.startsWith('<table') ||
            trimmed.startsWith('<tr') ||
            trimmed.startsWith('<th') ||
            trimmed.startsWith('<td') ||
            trimmed.startsWith('__CODEBLOCK_') ||
            trimmed.startsWith('__TOOLBLOCK_') ||
            trimmed.startsWith('|') ||
            trimmed.match(/^[-=]{3,}$/)) {
            prevWasEmpty = false;
            return line;
        }

        prevWasEmpty = false;
        return line;
    });
    result = formattedLines.join('\n');

    // Line breaks - but collapse multiple empty lines
    result = result.replace(/\n{3,}/g, '\n\n');  // Max 2 newlines
    result = result.replace(/\n/g, '<br>');
    // Collapse multiple <br> tags
    result = result.replace(/(<br>){3,}/g, '<br><br>');

    // Restore code blocks
    codeBlocks.forEach((block, idx) => {
        result = result.replace(`__CODEBLOCK_${idx}__`, block);
    });

    // Restore tool blocks - remove surrounding <br> tags for cleaner look
    toolBlocks.forEach((block, idx) => {
        // Remove <br> right before and after tool blocks
        result = result.replace(new RegExp(`(<br>)*__TOOLBLOCK_${idx}__(<br>)*`, 'g'), block);
    });

    return result;
}

// Format streaming tool blocks - detect and render tool blocks during streaming
function formatStreamingToolBlocks(text, toolBlocksArray) {
    const lines = text.split('\n');
    const resultLines = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];
        const toolMatch = matchToolLine(line);

        if (toolMatch) {
            const { toolConfig, content: firstLine, lineRange, searchQuery } = toolMatch;

            // Collect command lines
            let commandLines = [firstLine];
            let toolLineRange = lineRange; // Store line range if present
            let toolSearchQuery = searchQuery; // Store search query if present
            let resultLines_tool = [];
            let codeDiffLines = [];
            let hasResult = false;
            let isComplete = false;
            let hasError = false;
            let inCodeDiff = false;
            i++;

            // Look ahead for more content
            let expectingResultContent = false; // Track if we just saw standalone ↳

            while (i < lines.length) {
                const nextLine = lines[i];
                const trimmed = nextLine.trim();

                // Check if this is a result line (starts with ↳)
                if (trimmed.startsWith(TOOL_CONFIG.resultPrefix)) {
                    hasResult = true;
                    const resultContent = trimmed.substring(1).trim();
                    if (resultContent) {
                        resultLines_tool.push(resultContent);
                        expectingResultContent = false;
                    } else {
                        // Standalone ↳ - next line is the content
                        expectingResultContent = true;
                    }

                    // Check for error
                    if (resultContent.toLowerCase().includes('error') ||
                        resultContent.toLowerCase().includes('traceback')) {
                        hasError = true;
                    }

                    // Check if this is an "Edited" result - expect code diff lines to follow
                    if (resultContent.toLowerCase().includes('edited') &&
                        (resultContent.toLowerCase().includes('addition') || resultContent.toLowerCase().includes('removal'))) {
                        inCodeDiff = true;
                    }

                    // Check if this is a completion keyword (but not if in code diff mode)
                    const lower = resultContent.toLowerCase();
                    const isEnd = TOOL_CONFIG.resultEndKeywords.some(kw => lower.includes(kw));
                    if (isEnd && !inCodeDiff) {
                        isComplete = true;
                        i++;
                        break;
                    }
                    i++;
                }
                // Content following a standalone ↳
                else if (expectingResultContent && trimmed && !matchToolLine(nextLine)) {
                    resultLines_tool.push(trimmed);
                    expectingResultContent = false;

                    // Check for error/completion in continuation line
                    const lower = trimmed.toLowerCase();
                    if (lower.includes('error') || lower.includes('traceback')) {
                        hasError = true;
                    }
                    if (lower.includes('edited') &&
                        (lower.includes('addition') || lower.includes('removal'))) {
                        inCodeDiff = true;
                    }
                    const isEnd = TOOL_CONFIG.resultEndKeywords.some(kw => lower.includes(kw));
                    if (isEnd && !inCodeDiff) {
                        isComplete = true;
                        i++;
                        break;
                    }
                    i++;
                }
                // New tool starting - end current block
                else if (matchToolLine(nextLine)) {
                    isComplete = hasResult; // Complete if we have results
                    break;
                }
                // Code diff lines (e.g., "9 - old code" or "37 + new code") - NO ↳ prefix
                else if (inCodeDiff && isCodeDiffLine(trimmed)) {
                    codeDiffLines.push(trimmed);
                    i++;
                }
                // Empty line after results = end of block
                else if (trimmed === '' && hasResult) {
                    isComplete = true;
                    i++;
                    break;
                }
                // More command content (before results)
                else if (!hasResult) {
                    commandLines.push(nextLine);
                    i++;
                }
                // In code diff but not a diff line - end block
                else if (inCodeDiff) {
                    isComplete = true;
                    break;
                }
                // Text after results = end of block
                else {
                    isComplete = true;
                    break;
                }
            }

            // Render the tool block (streaming or complete)
            const idx = toolBlocksArray.length;
            const html = renderStreamingToolBlock({
                toolType: toolConfig.type,
                name: toolConfig.name,
                icon: toolConfig.icon,
                command: commandLines.join('\n').trim(),
                results: resultLines_tool,
                codeDiff: codeDiffLines,
                hasError: hasError,
                isStreaming: !isComplete,
                lineRange: toolLineRange,
                searchQuery: toolSearchQuery
            });
            toolBlocksArray.push(html);
            resultLines.push(`__TOOLBLOCK_${idx}__`);
            continue;
        }

        // Regular line
        resultLines.push(line);
        i++;
    }

    return resultLines.join('\n');
}

// Render a streaming tool block (with loading indicator if incomplete)
// When complete, use same structure as renderToolBlock for consistency
function renderStreamingToolBlock(tool) {
    const typeClass = `tool-${tool.toolType}`;
    const errorClass = tool.hasError ? ' has-error' : '';
    const streamingClass = tool.isStreaming ? ' streaming' : '';

    let html = `<div class="tool-block ${typeClass}${errorClass}${streamingClass}">`;

    // For line range reads, show a cleaner header with just filename and range
    if (tool.lineRange) {
        const fileName = tool.command.split('/').pop(); // Get just the filename
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="line-range">lines ${tool.lineRange.start}-${tool.lineRange.end}</span></div>`;
    }
    // For file search reads, show filename and search query badge
    else if (tool.searchQuery) {
        const fileName = tool.command.split('/').pop(); // Get just the filename
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="search-query"><i class="fas fa-search"></i> ${escapeHtml(tool.searchQuery)}</span></div>`;
    } else {
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}`;
        // Add copy button for Terminal blocks
        if (tool.toolType === 'terminal') {
            const encodedCommand = btoa(unescape(encodeURIComponent(tool.command)));
            html += `<button class="tool-copy-btn" data-command="${encodedCommand}" title="Copy command"><i class="fas fa-copy"></i></button>`;
        }
        html += `</div>`;
        // Command section - wrap in <code> like final version
        html += `<div class="tool-command"><code>${escapeHtml(tool.command)}</code></div>`;
    }

    // Results section - use same structure as renderToolBlock (tool-result with result-line)
    const filteredResults = tool.results ? tool.results.filter(r => r && r.trim()) : [];
    if (filteredResults.length > 0) {
        html += `<div class="tool-result">`;
        filteredResults.forEach(r => {
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

    html += `</div>`;

    // Render code diff lines (for Edit File blocks) - on the fly during streaming
    if (tool.codeDiff && tool.codeDiff.length > 0) {
        html += renderCodeDiffBlock(tool.codeDiff, tool.isStreaming);
    }

    return html;
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

// Check if a result line indicates successful end of tool output
function isSuccessEndLine(text) {
    const lower = text.toLowerCase().trim();

    // Exact phrase matches - these indicate definitive completion
    const exactPhrases = [
        'command completed',
        'process completed',
        'added tasks successfully',
        'updated tasks',
        'no results'
    ];
    if (exactPhrases.some(phrase => lower.includes(phrase))) {
        return true;
    }

    // Start-of-line patterns - e.g., "Read 14 lines", "Found 5 matches", "Listed 37 entries"
    // These only indicate completion when at the START of the line
    // This prevents matching "found" inside "unused code found"
    const startPatterns = ['read ', 'listed ', 'wrote ', 'found '];
    return startPatterns.some(p => lower.startsWith(p));
}

// Check if a line looks like a code diff line (e.g., "589 + // comment" or "590 - old code" or "38 -" for empty line removal)
function isCodeDiffLine(text) {
    const trimmed = text.trim();
    // Match: number followed by + or - (with optional content after)
    // Examples: "38 -" (empty line), "9 - old code", "37 + new code"
    return /^\d+\s*[+-](\s|$)/.test(trimmed);
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

// Parse tool blocks from text - accurate boundary detection
function parseToolBlocks(text) {
    const lines = text.split('\n');
    const result = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];
        const toolMatch = matchToolLine(line);

        // DEBUG: Log tool matching for Add Tasks
        if (line.includes('Add Tasks') || line.includes('Update Tasks')) {
            console.log('DEBUG parseToolBlocks:', { line, toolMatch, i });
        }

        if (toolMatch) {
            const { toolConfig, content: firstLine, lineRange, searchQuery } = toolMatch;

            // Collect command lines until we hit a result line
            let commandLines = [firstLine];
            let resultLines = [];
            let hasError = false;
            let inStackTrace = false;
            let foundEndResult = false;
            let toolLineRange = lineRange; // Store line range if present
            let toolSearchQuery = searchQuery; // Store search query if present
            i++;

            // Track if this is an Edit File block with code diffs
            let inCodeDiff = false;
            let codeDiffLines = [];
            let expectingResultContent = false; // Track if we just saw standalone ↳

            while (i < lines.length && !foundEndResult) {
                const nextLine = lines[i];
                const trimmed = nextLine.trim();

                // DEBUG: Log result line parsing for task blocks
                if (toolConfig.type === 'task') {
                    console.log('DEBUG task parsing:', { i, trimmed, startsWithArrow: trimmed.startsWith(TOOL_CONFIG.resultPrefix), resultLines: [...resultLines] });
                }

                // Check if this is a result line (starts with ↳)
                if (trimmed.startsWith(TOOL_CONFIG.resultPrefix)) {
                    const resultContent = trimmed.substring(1).trim();
                    if (resultContent) {
                        resultLines.push(resultContent);
                        expectingResultContent = false;
                    } else {
                        // Standalone ↳ - next line is the content
                        expectingResultContent = true;
                    }

                    // Track if we have an error/traceback starting
                    if (isErrorStartLine(resultContent)) {
                        hasError = true;
                        const lower = resultContent.toLowerCase();
                        const hasTraceIndicator = lower.includes('traceback') ||
                                                  lower.includes('file "') ||
                                                  lower.includes('exception');
                        inStackTrace = hasTraceIndicator;
                        // Don't end block on "command error" - the actual error message follows
                        // Continue collecting lines until we hit a new tool or empty line
                    }

                    // Check if this is an "Edited" result - expect code diff lines to follow
                    if (resultContent.toLowerCase().includes('edited') &&
                        (resultContent.toLowerCase().includes('addition') || resultContent.toLowerCase().includes('removal'))) {
                        inCodeDiff = true;
                    }

                    // Only end on success keywords (not error) and not in code diff mode
                    if (isSuccessEndLine(resultContent) && !hasError && !inCodeDiff) {
                        foundEndResult = true;
                    }
                    i++;
                }
                // Content following a standalone ↳
                else if (expectingResultContent && trimmed && !matchToolLine(nextLine)) {
                    resultLines.push(trimmed);
                    expectingResultContent = false;

                    // Check for error/completion in continuation line
                    const lower = trimmed.toLowerCase();
                    if (isErrorStartLine(trimmed)) {
                        hasError = true;
                    }
                    if (lower.includes('edited') &&
                        (lower.includes('addition') || lower.includes('removal'))) {
                        inCodeDiff = true;
                    }
                    if (isSuccessEndLine(trimmed) && !hasError && !inCodeDiff) {
                        foundEndResult = true;
                    }
                    i++;
                }
                // Check if new tool is starting
                else if (matchToolLine(nextLine)) {
                    break; // New tool starting, end current block
                }
                // Code diff lines (e.g., "9 - old code" or "37 + new code") - NO ↳ prefix
                else if (inCodeDiff && isCodeDiffLine(trimmed)) {
                    codeDiffLines.push(trimmed);
                    i++;
                }
                // Empty line
                else if (trimmed === '') {
                    // In code diff mode, empty line ends the diff section
                    if (inCodeDiff && codeDiffLines.length > 0) {
                        break;
                    }
                    if (resultLines.length > 0 && !inStackTrace) {
                        break;
                    }
                    i++;
                }
                // If we're in a stack trace, collect continuation lines
                else if (inStackTrace) {
                    if (isExplanatoryText(trimmed)) {
                        inStackTrace = false;
                        break;
                    }
                    resultLines.push(trimmed);
                    i++;
                }
                // Command continuation (before any results)
                else if (resultLines.length === 0) {
                    commandLines.push(nextLine);
                    i++;
                }
                // In code diff mode but not a diff line - end block
                else if (inCodeDiff) {
                    break;
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
                hasError: hasError,
                lineRange: toolLineRange,
                searchQuery: toolSearchQuery
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

    // For line range reads, show a cleaner header with just filename and range
    if (tool.lineRange) {
        const fileName = tool.command.split('/').pop(); // Get just the filename
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="line-range">lines ${tool.lineRange.start}-${tool.lineRange.end}</span></div>`;
    }
    // For file search reads, show filename and search query badge
    else if (tool.searchQuery) {
        const fileName = tool.command.split('/').pop(); // Get just the filename
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="search-query"><i class="fas fa-search"></i> ${escapeHtml(tool.searchQuery)}</span></div>`;
    } else {
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}`;
        // Add copy button for Terminal blocks
        if (tool.toolType === 'terminal') {
            // Base64 encode the command to handle special characters
            const encodedCommand = btoa(unescape(encodeURIComponent(tool.command)));
            html += `<button class="tool-copy-btn" data-command="${encodedCommand}" title="Copy command"><i class="fas fa-copy"></i></button>`;
        }
        html += `</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(tool.command)}</code></div>`;
    }

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
        } else if (tool.toolType === 'task') {
            // Task block rendering - show tasks as a clean list
            html += `<div class="tool-result task-list">`;
            tool.results.filter(r => r && r.trim()).forEach(r => {
                let resultHtml = escapeHtml(r);
                const lower = r.toLowerCase();

                // Style based on content
                if (lower.includes('added tasks') || lower.includes('updated tasks')) {
                    resultHtml = `<span class="result-success">${resultHtml}</span>`;
                } else if (lower.includes('→')) {
                    // Status change like "Task → In Progress"
                    resultHtml = `<span class="task-status">${resultHtml}</span>`;
                } else if (r.includes('(') && r.includes(')')) {
                    // Task with description like "Task Name (description)"
                    const parts = r.match(/^([^(]+)\(([^)]+)\)$/);
                    if (parts) {
                        resultHtml = `<span class="task-name">${escapeHtml(parts[1].trim())}</span><span class="task-desc">${escapeHtml(parts[2])}</span>`;
                    }
                }
                html += `<div class="result-line"><span class="result-arrow">↳</span> ${resultHtml}</div>`;
            });
            html += `</div>`;
        } else {
            // Normal result rendering
            html += `<div class="tool-result">`;
            tool.results.forEach(r => {
                let resultHtml = escapeHtml(r);
                if (r.toLowerCase().includes('error')) {
                    resultHtml = `<span class="result-error">${resultHtml}</span>`;
                } else if (r.toLowerCase().includes('completed') || r.toLowerCase().includes('successfully')) {
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
        html += renderCodeDiffBlock(tool.codeDiff);
        return html; // Already closed tool-block
    }

    html += `</div>`;
    return html;
}

// Render a collapsible code diff block
function renderCodeDiffBlock(codeDiffLines, isStreaming = false) {
    // Count additions and removals
    let additions = 0, removals = 0;
    codeDiffLines.forEach(line => {
        if (/^\d+\s*\+/.test(line)) additions++;
        else if (/^\d+\s*-/.test(line)) removals++;
    });

    const streamingClass = isStreaming ? ' streaming' : '';
    const collapsedClass = isStreaming ? '' : ' collapsed'; // Collapsed by default when not streaming
    let html = `<div class="tool-code-diff-wrapper${streamingClass}${collapsedClass}" onclick="toggleCodeDiff(event, this)">`;

    // Clickable header
    html += `<div class="tool-code-diff-header">`;
    html += `<span class="diff-arrow">↳</span>`;
    html += `<span class="diff-label">Code Changes</span>`;
    html += `<span class="diff-stats">`;
    if (additions > 0) html += `<span class="diff-stat-add">+${additions}</span>`;
    if (removals > 0) html += `<span class="diff-stat-remove">-${removals}</span>`;
    html += `</span>`;
    html += `<i class="fas fa-chevron-down diff-toggle-icon"></i>`;
    html += `</div>`;

    // Code diff content
    html += `<div class="tool-code-diff">`;
    codeDiffLines.forEach(line => {
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

    return html;
}

// Toggle code diff collapse/expand
function toggleCodeDiff(event, wrapper) {
    // Don't toggle if clicking inside the diff content
    if (event.target.closest('.tool-code-diff')) return;
    wrapper.classList.toggle('collapsed');
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

    // Table copy button
    const tableCopyBtn = e.target.closest('.table-copy-btn');
    if (tableCopyBtn) {
        e.preventDefault();
        e.stopPropagation();
        copyTable(tableCopyBtn);
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

// Copy table to clipboard
function copyTable(btn) {
    const encodedTable = btn.getAttribute('data-table');
    if (!encodedTable) return;

    // Decode from base64
    const tableMarkdown = decodeURIComponent(escape(atob(encodedTable)));

    navigator.clipboard.writeText(tableMarkdown).then(() => {
        // Show success feedback
        const icon = btn.querySelector('i');
        icon.className = 'fas fa-check';
        btn.classList.add('copied');
        setTimeout(() => {
            icon.className = 'fas fa-copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy table:', err);
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
    // 0) Headings followed by a list (e.g., "Key Points" then bullets)
    text = text.replace(/^([A-Z][A-Za-z0-9\s\-]{2,50})\s*$(?=\n[\s]*([•\-\*]|\d+\.)\s+)/gm, (match, header) => {
        if (!header.includes('|')) {
            return `<div class="section-header"><strong>${header}</strong></div>`;
        }
        return match;
    });

    // Match lines that look like section headers:
    // 1. Bold text on its own line
    text = text.replace(/^(<strong>([^<]+)<\/strong>)\s*$/gm, '<div class="section-header">$1</div>');

    // 2. Text ending with colon (like "Summary:", "Key findings:", "Process Details:")
    text = text.replace(/^([A-Z][A-Za-z0-9\s\-]+):\s*$/gm, (match, header) => {
        // Only if it looks like a section header (not too long, no pipes for tables)
        if (header.length < 60 && !header.includes('|')) {
            return `<div class="section-header"><strong>${header}</strong></div>`;
        }
        return match;
    });

    // 2b. Numbered standalone headings like "1. Overview"
    text = text.replace(/^\s*(\d+)[\.\)]\s+([A-Z][A-Za-z0-9\s\-]{2,50})\s*$/gm, (match, num, header) => {
        if (!header.includes('|')) {
            return `<div class="section-header"><strong>${num}. ${header}</strong></div>`;
        }
        return match;
    });

    // 3. Capitalized phrases that are short introductory lines (without colon but standalone)
    text = text.replace(/^([A-Z][A-Za-z\s]{3,40})\s*$/gm, (match, header) => {
        // Common section header words
        const headerKeywords = ['Summary', 'Details', 'Overview', 'Findings', 'Results',
            'Analysis', 'Notes', 'Steps', 'Instructions', 'Explanation', 'Solution',
            'Problem', 'Issue', 'Cause', 'Fix', 'Changes', 'Updates', 'Status'];
        const hasKeyword = headerKeywords.some(kw => header.includes(kw));
        if (hasKeyword && !header.includes('|')) {
            return `<div class="section-header"><strong>${header}</strong></div>`;
        }
        return match;
    });

    // 4. All-caps short lines
    text = text.replace(/^([A-Z][A-Z0-9\s\-]{2,40})\s*$/gm, (match, header) => {
        if (!header.includes('|')) {
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
            // Split and keep empty cells (slice removes leading/trailing empty from | split)
            const headerParts = header.split('|').slice(1, -1);
            const headerCells = headerParts.map(c => `<th>${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cellParts = row.split('|').slice(1, -1);
                const cells = cellParts.map(c => `<td>${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            // Encode original markdown for copy
            const encodedTable = btoa(unescape(encodeURIComponent(match.trim())));
            return `<div class="table-wrapper"><button class="table-copy-btn" data-table="${encodedTable}" title="Copy table"><i class="fas fa-copy"></i></button><table class="md-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
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

    // Key: Value lines (lightweight emphasis for readability)
    text = text.replace(/^([A-Z][A-Za-z0-9\s\-\/]{2,30}):\s+(.{1,160})$/gm, (match, key, value) => {
        if (key.includes('|') || value.includes('|')) return match;
        if (value.includes('http') || value.length > 160) return match;
        return `<div class="sub-item"><span class="sub-arrow">↳</span><strong>${key}:</strong> ${value}</div>`;
    });

    // Lists with nested support
    const lines = text.split('\n');
    const processedLines = [];
    const listStack = []; // Stack to track nested lists: [{type: 'ul'|'ol', indent: number}]

    for (const line of lines) {
        // Match bullet or numbered list items with their indentation
        const bulletMatch = line.match(/^([\s]*)[•\-\*]\s+(.+)$/);
        const numberedMatch = line.match(/^([\s]*)(\d+)\.\s+(.+)$/);

        if (bulletMatch || numberedMatch) {
            const indent = (bulletMatch ? bulletMatch[1] : numberedMatch[1]).length;
            const itemType = bulletMatch ? 'ul' : 'ol';
            const content = bulletMatch ? bulletMatch[2] : numberedMatch[3];
            const num = numberedMatch ? parseInt(numberedMatch[2], 10) : null;

            // Close lists that are deeper than current indent
            while (listStack.length > 0 && listStack[listStack.length - 1].indent >= indent) {
                const closed = listStack.pop();
                processedLines.push(closed.type === 'ul' ? '</ul></li>' : '</ol></li>');
            }

            // Check if we need to start a new list or continue existing one
            const currentList = listStack.length > 0 ? listStack[listStack.length - 1] : null;

            if (!currentList || indent > currentList.indent) {
                // Starting a new nested list
                if (currentList && indent > currentList.indent) {
                    // Remove the closing </li> from the last item to nest inside it
                    const lastLine = processedLines[processedLines.length - 1];
                    if (lastLine && lastLine.endsWith('</li>')) {
                        processedLines[processedLines.length - 1] = lastLine.slice(0, -5);
                    }
                }
                if (itemType === 'ul') {
                    processedLines.push('<ul class="md-list">');
                } else {
                    processedLines.push(`<ol class="md-list" start="${num}">`);
                }
                listStack.push({ type: itemType, indent: indent });
            } else if (currentList.type !== itemType) {
                // Switching list type at same level
                processedLines.push(currentList.type === 'ul' ? '</ul>' : '</ol>');
                listStack.pop();
                if (itemType === 'ul') {
                    processedLines.push('<ul class="md-list">');
                } else {
                    processedLines.push(`<ol class="md-list" start="${num}">`);
                }
                listStack.push({ type: itemType, indent: indent });
            }

            // Add the list item
            if (itemType === 'ul') {
                processedLines.push(`<li>${content}</li>`);
            } else {
                processedLines.push(`<li value="${num}">${content}</li>`);
            }
        } else {
            // Not a list item - close all open lists
            while (listStack.length > 0) {
                const closed = listStack.pop();
                if (listStack.length > 0) {
                    processedLines.push(closed.type === 'ul' ? '</ul></li>' : '</ol></li>');
                } else {
                    processedLines.push(closed.type === 'ul' ? '</ul>' : '</ol>');
                }
            }
            processedLines.push(line);
        }
    }
    // Close any remaining open lists
    while (listStack.length > 0) {
        const closed = listStack.pop();
        if (listStack.length > 0) {
            processedLines.push(closed.type === 'ul' ? '</ul></li>' : '</ol></li>');
        } else {
            processedLines.push(closed.type === 'ul' ? '</ul>' : '</ol>');
        }
    }
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
    'AI is thinking...', 'Receiving response...', 'Finalizing response...',
    'Summarizing...', 'Processing...', 'Analyzing...', 'Generating response...',
    // Backend status messages
    'Initializing Augment...', 'Ready!', 'Indexing codebase...', 'Indexing complete!',
    'Sending request...', 'Executing tools...', 'Processing tools...',
    // Patterns that include elapsed time like "AI is thinking... (5s)"
    'Reconnecting to Augment...'
];

// Check if a message matches generic status patterns (including time suffixes)
function isGenericStatus(message) {
    // Exact or partial match
    if (genericStatuses.some(g => message.includes(g) || g.includes(message))) {
        return true;
    }
    // Pattern match for messages with time like "AI is thinking... (5s)"
    const patterns = [
        /^AI is thinking/i,
        /^Sending request/i,
        /^Executing tools/i,
        /^Processing tools/i,
        /^Receiving response/i,
        /^Indexing codebase/i,
        /^Initializing/i,
        /^Connecting/i,
        /^Starting/i,
        /^Waiting/i
    ];
    return patterns.some(p => p.test(message));
}

// Get appropriate icon for status message
function getStatusIcon(message) {
    const lowerMsg = message.toLowerCase();
    if (lowerMsg.includes('connecting') || lowerMsg.includes('starting') || lowerMsg.includes('initializing')) {
        return 'fa-plug';
    } else if (lowerMsg.includes('indexing')) {
        return 'fa-database';
    } else if (lowerMsg.includes('sending')) {
        return 'fa-paper-plane';
    } else if (lowerMsg.includes('waiting') || lowerMsg.includes('thinking')) {
        return 'fa-brain';
    } else if (lowerMsg.includes('receiving') || lowerMsg.includes('streaming')) {
        return 'fa-download';
    } else if (lowerMsg.includes('executing') || lowerMsg.includes('tool')) {
        return 'fa-wrench';
    } else if (lowerMsg.includes('processing') || lowerMsg.includes('analyzing')) {
        return 'fa-cog';
    } else if (lowerMsg.includes('summarizing')) {
        return 'fa-compress-alt';
    } else if (lowerMsg.includes('generating')) {
        return 'fa-magic';
    } else if (lowerMsg.includes('ready') || lowerMsg.includes('complete')) {
        return 'fa-check-circle';
    }
    return 'fa-circle-notch';
}

// Show/hide typing indicator with status message
function showTypingIndicator(statusMessage = 'Thinking...') {
    const statusBar = document.getElementById('inputStatusBar');
    if (!statusBar) return;

    // Show status bar and update text
    statusBar.style.display = 'flex';
    const statusText = statusBar.querySelector('.status-text');
    const statusIcon = statusBar.querySelector('.status-icon');
    if (statusText) statusText.textContent = statusMessage;
    if (statusIcon) {
        const newIcon = getStatusIcon(statusMessage);
        statusIcon.className = `fas ${newIcon} fa-spin status-icon`;
    }
}

// Get current status log (for backward compatibility, but now uses status bar)
function getCurrentStatusLog() {
    return document.getElementById('inputStatusBar');
}

// Update typing status - now updates the fixed status bar above input
function updateTypingStatus(message) {
    const statusBar = document.getElementById('inputStatusBar');
    if (!statusBar) return;

    // Make sure status bar is visible
    statusBar.style.display = 'flex';

    const statusText = statusBar.querySelector('.status-text');
    const statusIcon = statusBar.querySelector('.status-icon');

    if (statusText) statusText.textContent = message;
    if (statusIcon) {
        const newIcon = getStatusIcon(message);
        statusIcon.className = `fas ${newIcon} fa-spin status-icon`;
    }
}

function hideTypingIndicator() {
    const statusBar = document.getElementById('inputStatusBar');
    if (statusBar) statusBar.style.display = 'none';

    // Also clean up any old status logs that might still exist
    document.getElementById('typingIndicator')?.remove();
    document.querySelectorAll('.status-log').forEach(log => log.remove());
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

// Load settings from localStorage (instant, no server call)
function loadSettings() {
    const theme = localStorage.getItem('theme');
    const themeSelect = document.getElementById('themeSelect');
    const savedWorkspace = localStorage.getItem('workspace');
    const savedModel = localStorage.getItem('currentModel');
    const savedModels = localStorage.getItem('availableModels');

    if (theme) {
        applyTheme(theme);
        if (themeSelect) themeSelect.value = theme;
    }

    if (savedWorkspace) {
        currentWorkspace = savedWorkspace;
        updateWorkspaceDisplay();
    }

    // Restore model from cache for instant UI
    if (savedModel) {
        currentModel = savedModel;
    }
    if (savedModels) {
        try {
            availableModels = JSON.parse(savedModels);
            populateModelSelect();
        } catch (e) {
            console.log('[INIT] Failed to parse cached models');
        }
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

// Browse workspace directories (toggle)
function browseWorkspace() {
    console.log('browseWorkspace called');
    const modal = document.getElementById('browserModal');
    if (!modal) {
        console.error('browserModal not found');
        return;
    }
    // Toggle: if already open, close it
    if (modal.classList.contains('active')) {
        modal.classList.remove('active');
        return;
    }
    browserCurrentPath = currentWorkspace || '~';
    const pathEl = document.getElementById('browserPath');
    const listEl = document.getElementById('browserList');
    if (pathEl) pathEl.textContent = browserCurrentPath;
    if (listEl) listEl.innerHTML = '';  // Clear folder list on open
    modal.classList.add('active');
    console.log('browserModal activated');
}

// Load directory contents from server
async function loadBrowserDirectory(path) {
    console.log('loadBrowserDirectory called with path:', path);
    const pathEl = document.getElementById('browserPath');
    const listEl = document.getElementById('browserList');
    console.log('listEl:', listEl);

    if (pathEl) pathEl.textContent = path;
    if (listEl) listEl.innerHTML = '<div class="browser-loading"><i class="fas fa-spinner fa-spin"></i></div>';

    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (data.error) {
            if (listEl) listEl.innerHTML = `<div class="browser-error">${data.error}</div>`;
            return;
        }

        browserCurrentPath = data.current;
        if (pathEl) pathEl.textContent = data.current;

        if (!listEl) return;

        let html = '';

        // Add parent directory link if not at root
        if (data.parent && data.parent !== data.current) {
            html += `<div class="browser-item browser-parent" data-path="${encodeURIComponent(data.parent)}">
                <i class="fas fa-level-up-alt"></i>
                <span>..</span>
            </div>`;
        }

        if (data.items.length === 0 && !html) {
            listEl.innerHTML = '<div class="browser-empty">No subdirectories</div>';
            return;
        }

        html += data.items.map(item => `
            <div class="browser-item" data-path="${encodeURIComponent(item.path)}">
                <i class="fas fa-folder"></i>
                <span>${item.name}</span>
            </div>
        `).join('');

        listEl.innerHTML = html;
        console.log('Rendered', data.items.length, 'items');

        // Add click handlers using event delegation
        listEl.querySelectorAll('.browser-item').forEach(el => {
            el.onclick = function(e) {
                e.stopPropagation();
                const itemPath = decodeURIComponent(this.getAttribute('data-path'));
                console.log('Clicked folder:', itemPath);
                navigateToDir(itemPath);
            };
        });
    } catch (error) {
        console.error('Error loading directory:', error);
        if (listEl) listEl.innerHTML = '<div class="browser-error">Failed to load directory</div>';
    }
}

// Navigate to a specific directory
function navigateToDir(path) {
    browserCurrentPath = path;
    loadBrowserDirectory(path);
}

// Select current directory from browser
async function selectCurrentDir() {
    const workspaceInput = document.getElementById('workspaceInput');
    if (workspaceInput) workspaceInput.value = browserCurrentPath;
    currentWorkspace = browserCurrentPath;
    closeBrowser();
    updateWorkspaceDisplay();

    // Save workspace to server without opening settings modal
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace: currentWorkspace })
        });
        const data = await response.json();
        if (data.status === 'success') {
            localStorage.setItem('workspace', currentWorkspace);
            showWorkspaceToast('Workspace changed');
        }
    } catch (error) {
        console.error('Error saving workspace:', error);
    }
}

// Show simple toast below workspace badge
function showWorkspaceToast(message) {
    // Remove any existing toast
    const existing = document.getElementById('workspaceToast');
    if (existing) existing.remove();

    const badge = document.getElementById('workspaceBadge');
    if (!badge) return;

    const toast = document.createElement('div');
    toast.id = 'workspaceToast';
    toast.textContent = message;
    toast.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        margin-top: 4px;
        padding: 4px 10px;
        background: var(--bg-secondary);
        border: 1px solid var(--primary);
        border-radius: 4px;
        font-size: 0.7rem;
        color: var(--primary);
        white-space: nowrap;
        z-index: 1001;
        animation: fadeIn 0.2s ease;
    `;

    badge.style.position = 'relative';
    badge.appendChild(toast);

    setTimeout(() => toast.remove(), 2000);
}

// Navigate to home directory and show folder structure
function navigateToHome() {
    console.log('navigateToHome called');
    loadBrowserDirectory('~');
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
    // Reset to default width when opening
    if (sidebarOpen) {
        sidebar.style.width = '280px';
    }
}

// Sidebar resize functionality
function initSidebarResizer() {
    const sidebar = document.getElementById('sidebar');
    const resizer = document.getElementById('sidebarResizer');
    if (!resizer || !sidebar) return;

    const MIN_WIDTH = 180;
    const MAX_WIDTH = 450;
    const CLOSE_THRESHOLD = 100; // Close sidebar if dragged below this width

    let isResizing = false;
    let startX = 0;
    let startWidth = 0;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        sidebar.classList.add('resizing');
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;

        const deltaX = e.clientX - startX;
        let newWidth = startWidth + deltaX;

        // Check if should close
        if (newWidth < CLOSE_THRESHOLD) {
            sidebar.style.opacity = Math.max(0.3, newWidth / CLOSE_THRESHOLD);
        } else {
            sidebar.style.opacity = '1';
        }

        // Clamp width within bounds (but allow going below for close gesture)
        if (newWidth >= MIN_WIDTH) {
            newWidth = Math.min(newWidth, MAX_WIDTH);
            sidebar.style.width = newWidth + 'px';
        } else if (newWidth >= 0) {
            sidebar.style.width = newWidth + 'px';
        }
    });

    document.addEventListener('mouseup', () => {
        if (!isResizing) return;
        isResizing = false;
        sidebar.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        sidebar.style.opacity = '1';

        const currentWidth = sidebar.offsetWidth;

        // Close sidebar if below threshold
        if (currentWidth < CLOSE_THRESHOLD) {
            sidebar.style.width = '';
            sidebarOpen = false;
            sidebar.classList.add('collapsed');
            localStorage.setItem('sidebarOpen', 'false');
        } else {
            // Ensure minimum width
            const finalWidth = Math.max(currentWidth, MIN_WIDTH);
            sidebar.style.width = finalWidth + 'px';
        }
    });
}

// Initialize sidebar resizer on DOM load
document.addEventListener('DOMContentLoaded', initSidebarResizer);

// Load chats from server
async function loadChatsFromServer() {
    const url = '/api/chats';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const chats = await response.json();
        logResponse('GET', url, response.status, { chats_count: chats.length });
        // Cache chat list for instant reload
        localStorage.setItem('cachedChatList', JSON.stringify(chats));
        renderChatHistory(chats);
        return chats;  // Return chats array for caller to use
    } catch (error) {
        console.error('Failed to load chats:', error);
        return [];
    }
}

// Load cached chat list from localStorage (instant, no server call)
function loadCachedChatList() {
    try {
        const cached = localStorage.getItem('cachedChatList');
        if (cached) {
            return JSON.parse(cached);
        }
    } catch (e) {
        console.log('[INIT] Failed to parse cached chat list');
    }
    return null;
}

// Render chat history in sidebar
function renderChatHistory(chats) {
    const container = document.getElementById('chatHistory');
    if (!container) return;

    container.innerHTML = '';

    if (chats.length === 0) {
        container.innerHTML = `
            <div class="chat-history-empty">
                <i class="fas fa-comments"></i>
                <span>No conversations yet</span>
            </div>
        `;
        return;
    }

    chats.forEach(chat => {
        const item = document.createElement('div');
        const hasBgRequest = hasActiveRequest(chat.id);
        item.className = `chat-history-item ${chat.id === currentChatId ? 'active' : ''} ${hasBgRequest ? 'has-background-request' : ''}`;
        item.onclick = (e) => {
            if (!e.target.closest('.delete-chat-btn')) {
                loadChatFromServer(chat.id);
            }
        };

        // Format date
        const date = new Date(chat.updated_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        item.innerHTML = `
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
        // If already in an empty new chat, don't create another one
        if (chatHistory.length === 0 && currentChatId) {
            console.log('[NEW CHAT] Already in empty chat, skipping creation');
            return;
        }

        const oldChatId = currentChatId;

        // If there's an active request for the old chat, let it continue in background
        if (oldChatId && hasActiveRequest(oldChatId)) {
            console.log('[NEW CHAT] Letting request continue in background for:', oldChatId);
            // Update the background request with current streaming content
            const request = getActiveRequest(oldChatId);
            if (request && streamingContent) {
                request.streamingContent = streamingContent;
            }
            // Remove the streaming div from DOM (will be recreated when switching back)
            if (streamingMessageDiv) {
                streamingMessageDiv.remove();
            }
        } else if (currentChatId && chatHistory.length > 0) {
            // No active request - save any content before switching
            console.log('[NEW CHAT] Saving old chat before switching:', currentChatId);
            const oldChatHistory = [...chatHistory];

            // If there's streaming content (shouldn't happen if no active request, but just in case)
            if (streamingMessageDiv && streamingContent) {
                const index = oldChatHistory.length;
                const messageId = generateMessageId(oldChatId, index, streamingContent);
                oldChatHistory.push({ role: 'assistant', content: streamingContent, messageId });
                streamingMessageDiv.remove();
            }

            // Save to local cache immediately (reliable)
            saveChatToCache(oldChatId, oldChatHistory);

            // Save old chat to server in background (don't await)
            fetch(`/api/chats/${oldChatId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: oldChatHistory })
            }).then(() => markCacheSynced(oldChatId))
              .catch(err => console.error('[NEW CHAT] Failed to save old chat to server (cached locally):', err));
        }

        // Reset streaming state for new chat
        streamingMessageDiv = null;
        streamingContent = '';
        streamingFinalized = true;

        // DON'T abort the request - let it continue in background
        // Just clear the current abort controller reference
        currentAbortController = null;

        // Reset processing state for UI
        isProcessing = false;
        hideTypingIndicator();
        hideStopButton();
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('messageInput').disabled = false;

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
        console.log('[NEW CHAT] New chat created:', currentChatId);
    } catch (error) {
        console.error('Failed to create chat:', error);
        showNotification('Failed to create new chat');
    }
}

// Save current chat to server (with local cache backup)
async function saveCurrentChatToServer(allowEmpty = false) {
    if (!currentChatId) return;
    // Allow saving empty history when explicitly requested (e.g., during edit/retry)
    if (chatHistory.length === 0 && !allowEmpty) return;

    // Always save to local cache first (immediate, reliable)
    saveChatToCache(currentChatId, chatHistory, streamingContent);

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

        // Mark cache as synced on successful server save
        markCacheSynced(currentChatId);
        loadChatsFromServer();
    } catch (error) {
        console.error('[SAVE] Failed to save chat to server (cached locally):', error);
        // Data is still safe in local cache - will sync later
    }
}

// Load chat from server
async function loadChatFromServer(chatId) {
    console.log('[LOAD] Loading chat:', chatId);

    const oldChatId = currentChatId;

    // Save the OLD chat before switching (if switching to a different chat)
    if (oldChatId && oldChatId !== chatId) {
        // If there's an active request for the old chat, let it continue in background
        if (hasActiveRequest(oldChatId)) {
            console.log('[LOAD] Letting request continue in background for:', oldChatId);
            const request = getActiveRequest(oldChatId);
            if (request && streamingContent) {
                request.streamingContent = streamingContent;
            }
            if (streamingMessageDiv) {
                streamingMessageDiv.remove();
            }
        } else if (chatHistory.length > 0) {
            // No active request - save any content before switching
            console.log('[LOAD] Saving old chat before switching:', oldChatId);
            const oldChatHistory = [...chatHistory];

            if (streamingMessageDiv && streamingContent) {
                console.log('[LOAD] Including streaming content in old chat');
                const index = oldChatHistory.length;
                const messageId = generateMessageId(oldChatId, index, streamingContent);
                oldChatHistory.push({ role: 'assistant', content: streamingContent, messageId });
                streamingMessageDiv.remove();
            }

            saveChatToCache(oldChatId, oldChatHistory);
            fetch(`/api/chats/${oldChatId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: oldChatHistory })
            }).then(() => markCacheSynced(oldChatId))
              .catch(err => console.error('[LOAD] Failed to save old chat:', err));
        }

        // Reset streaming state for UI
        streamingMessageDiv = null;
        streamingContent = '';
        streamingFinalized = true;

        // DON'T abort - let background request continue
        currentAbortController = null;

        // Reset processing state for UI
        isProcessing = false;
        hideTypingIndicator();
        hideStopButton();
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('messageInput').disabled = false;
    }

    // Check if the target chat has an active background request
    const activeRequest = getActiveRequest(chatId);
    if (activeRequest) {
        console.log('[LOAD] Target chat has active background request, restoring state');
        currentChatId = chatId;
        chatHistory = activeRequest.chatHistory;
        streamingContent = activeRequest.streamingContent;
        localStorage.setItem('currentChatId', currentChatId);

        // Render the chat with current state
        const container = document.getElementById('chatMessages');
        container.innerHTML = '';
        chatHistory.forEach((msg, idx) => {
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

        // Create streaming message div for ongoing response
        if (streamingContent) {
            streamingMessageDiv = document.createElement('div');
            streamingMessageDiv.className = 'message assistant streaming';
            streamingMessageDiv.innerHTML = createMessageHTML('assistant', streamingContent, chatHistory.length, 'streaming');
            container.appendChild(streamingMessageDiv);
            addCodeCopyButtons(streamingMessageDiv);
        }

        // Restore UI state for active request
        isProcessing = true;
        currentAbortController = activeRequest.abortController;
        showTypingIndicator();
        showStopButton();
        if (activeRequest.statusMessage) {
            updateTypingStatus(activeRequest.statusMessage);
        }
        document.getElementById('sendBtn').disabled = true;
        document.getElementById('messageInput').disabled = true;

        setTimeout(() => container.scrollTop = container.scrollHeight, 50);
        loadChatsFromServer();
        return;
    }

    // Add cache-busting timestamp to prevent browser caching
    const url = `/api/chats/${chatId}?_t=${Date.now()}`;
    logRequest('GET', url);
    try {
        const response = await fetch(url, { cache: 'no-store' });
        const chat = await response.json();
        logResponse('GET', url, response.status, { messages_count: chat.messages?.length, error: chat.error });
        if (chat.error) {
            // Chat not found - don't create new chat here, let caller handle it
            console.log('[LOAD] Chat not found:', chatId);
            localStorage.removeItem('currentChatId');
            return false;
        }

        currentChatId = chatId;
        chatHistory = chat.messages || [];
        localStorage.setItem('currentChatId', currentChatId);
        console.log('[LOAD] Successfully loaded chat, currentChatId set to:', currentChatId);

        // Check if there's a pending stream (user refreshed during streaming)
        if (chat.streaming_status === 'pending' || chat.streaming_status === 'streaming') {
            console.log('[LOAD] Chat has pending stream, starting poll for updates');
            startPendingStreamPoll(chatId);
        }

        // Debug: log what we received from server
        console.log('[LOAD] Received from server:', chatHistory.length, 'messages');
        chatHistory.forEach((msg, i) => {
            console.log(`[LOAD]   [${i}] role=${msg.role}, content_length=${msg.content?.length || 0}, content_preview="${(msg.content || '').substring(0, 50)}..."`);
        });

        // Check local cache for newer data (recovery mechanism)
        const cachedData = loadChatFromCache(chatId);
        if (cachedData && cachedData.messages) {
            // Use cache if it has more messages or newer timestamp
            const serverMsgCount = chatHistory.length;
            const cacheMsgCount = cachedData.messages.length;
            if (cacheMsgCount > serverMsgCount) {
                console.log('[LOAD] Cache has more messages than server, using cache:', cacheMsgCount, 'vs', serverMsgCount);
                chatHistory = cachedData.messages;
                // Sync cache to server in background
                syncUnsyncedChats();
            }
        }

        // Only re-render if content has changed (avoid flash on refresh)
        const container = document.getElementById('chatMessages');
        const existingMsgCount = container.querySelectorAll('.message').length;
        const newMsgCount = chatHistory.length;

        // Skip re-render if same message count and same chat (content likely unchanged)
        if (existingMsgCount === newMsgCount && existingMsgCount > 0) {
            console.log('[LOAD] Skipping re-render, content unchanged');
        } else {
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
        }

        // Save to cache after successful load
        saveChatToCache(chatId, chatHistory);
        markCacheSynced(chatId);

        loadChatsFromServer();
    } catch (error) {
        console.error('Failed to load chat from server:', error);

        // Try to recover from local cache
        const cachedData = loadChatFromCache(chatId);
        if (cachedData && cachedData.messages && cachedData.messages.length > 0) {
            console.log('[LOAD] Server failed, recovering from cache');
            currentChatId = chatId;
            chatHistory = cachedData.messages;
            localStorage.setItem('currentChatId', currentChatId);

            const container = document.getElementById('chatMessages');
            container.innerHTML = '';
            chatHistory.forEach((msg, idx) => {
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
            return;
        }

        // No cache available - don't create new chat, let caller handle it
        localStorage.removeItem('currentChatId');
        return false;
    }
}

// Custom confirm dialog
function showConfirmDialog(message) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('confirmDialog');
        const messageEl = document.getElementById('confirmMessage');
        const cancelBtn = document.getElementById('confirmCancel');
        const deleteBtn = document.getElementById('confirmDelete');

        messageEl.textContent = message;
        dialog.classList.add('show');

        const cleanup = () => {
            dialog.classList.remove('show');
            cancelBtn.onclick = null;
            deleteBtn.onclick = null;
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        deleteBtn.onclick = () => {
            cleanup();
            resolve(true);
        };

        // Close on backdrop click
        dialog.onclick = (e) => {
            if (e.target === dialog) {
                cleanup();
                resolve(false);
            }
        };
    });
}

// Delete a chat
async function deleteChat(chatId, event) {
    if (event) event.stopPropagation();

    const confirmed = await showConfirmDialog('Delete this chat?');
    if (!confirmed) return;

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
    const confirmed = await showConfirmDialog('Delete all chat history? This cannot be undone.');
    if (!confirmed) return;

    // Clear localStorage immediately
    localStorage.removeItem('currentChatId');
    localStorage.removeItem('cachedChatList');
    chatHistory = [];

    // Clear main chat area immediately
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.innerHTML = WELCOME_HTML;
    }

    // Show cleared message immediately (before server response)
    const historyContainer = document.getElementById('chatHistory');
    if (historyContainer) {
        historyContainer.innerHTML = `
            <div class="chat-history-cleared">
                <i class="fas fa-check-circle"></i>
                <span>All chats cleared</span>
            </div>
        `;
    }

    // Delete from server and create new chat in background
    const url = '/api/chats/clear';
    logRequest('DELETE', url);
    fetch(url, { method: 'DELETE' })
        .then(response => response.json())
        .then(async data => {
            logResponse('DELETE', url, 200, data);
            // Create new chat immediately after server clears
            await createNewChat();
            // Then fade out the cleared message
            if (historyContainer) {
                const clearedMsg = historyContainer.querySelector('.chat-history-cleared');
                if (clearedMsg) {
                    clearedMsg.style.opacity = '0';
                }
            }
        })
        .catch(error => {
            console.error('Failed to clear chats on server:', error);
            // Still create new chat even if server fails
            createNewChat();
        });
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');

    // Color based on notification type
    let bgColor = 'var(--primary)';
    if (type === 'error') {
        bgColor = 'var(--error)';
    } else if (type === 'success') {
        bgColor = 'var(--success)';
    }

    notification.style.cssText = `
        position: fixed;
        bottom: 70px;
        left: 20px;
        background: ${bgColor};
        color: white;
        padding: 12px 24px;
        border-radius: 10px;
        z-index: 1001;
        animation: fadeIn 0.3s ease;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
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
            !e.target.closest('#workspaceBadge')) {
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
