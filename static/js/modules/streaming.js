import { state, activeRequests, CONSTANTS } from './state.js';
import { DOM } from './dom.js';
import { api, logRequest, logResponse } from './api.js';
import { saveChatToCache, markCacheSynced } from './cache.js';
import { showNotification, showTypingIndicator, hideTypingIndicator, updateTypingStatus } from './ui.js';
import { addMessage, generateMessageId, loadChatList, hideWelcome } from './chat.js';
import { formatMessageWithImages, clearSelectedImages } from './media.js';
import { formatMessage, formatMessageIncremental, resetIncrementalFormatCache, addCodeCopyButtons } from './markdown.js';
import { autoResize } from './dom.js';

let streamingMessageDiv = null;
let streamingContent = '';
let streamingFinalized = false;
let streamingRequestId = null;

export function getActiveRequestCount() {
    return activeRequests.size;
}

export function hasActiveRequest(chatId) {
    return activeRequests.has(chatId);
}

function createActiveRequest(chatId, abortController, requestId) {
    const request = {
        abortController,
        requestId,
        streamingContent: '',
        status: 'starting',
        statusMessage: '',
        chatHistory: [...state.chatHistory],
        startTime: Date.now()
    };
    activeRequests.set(chatId, request);
    console.log(`[BG] Created request for chat ${chatId}, active: ${activeRequests.size}`);
    return request;
}

function completeActiveRequest(chatId, finalContent, isBackground = false) {
    const request = activeRequests.get(chatId);
    if (request) {
        if (isBackground) {
            const index = request.chatHistory.length;
            const messageId = generateMessageId(chatId, index, finalContent);
            request.chatHistory.push({ role: 'assistant', content: finalContent, messageId });
            saveChatToCache(chatId, request.chatHistory);
            api.saveChat(chatId, request.chatHistory)
                .then(() => markCacheSynced(chatId));
        }
        activeRequests.delete(chatId);
        loadChatList();
    }
}

function startStreamingMessage(requestId) {
    streamingContent = '';
    streamingFinalized = false;
    streamingRequestId = requestId;
    resetIncrementalFormatCache();

    const container = DOM.get('chatMessages');
    if (!container) return;

    streamingMessageDiv = document.createElement('div');
    streamingMessageDiv.className = 'message assistant streaming';
    streamingMessageDiv.innerHTML = `
        <div class="message-content"><span class="streaming-cursor">▋</span></div>
    `;
    container.appendChild(streamingMessageDiv);
    container.scrollTop = container.scrollHeight;

    state.streamingMessageDiv = streamingMessageDiv;
    const providerSelect = DOM.get('providerSelectHeader');
    if (providerSelect) providerSelect.disabled = true;
}

function appendStreamingContent(content, requestId) {
    if (requestId !== streamingRequestId || !streamingMessageDiv) return;

    streamingContent += content;

    const contentDiv = streamingMessageDiv.querySelector('.message-content');
    if (contentDiv) {
        contentDiv.innerHTML = formatMessageIncremental(streamingContent);
    }

    const container = DOM.get('chatMessages');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function finalizeStreamingMessage(finalContent, requestId) {
    if (streamingFinalized) return;
    streamingFinalized = true;

    const content = finalContent || streamingContent;
    const messageId = generateMessageId(state.currentChatId, state.chatHistory.length, content);
    state.chatHistory.push({ role: 'assistant', content, messageId });

    if (streamingMessageDiv) {
        streamingMessageDiv.classList.remove('streaming');
        const contentDiv = streamingMessageDiv.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.innerHTML = formatMessage(content, false);
        }
        addCodeCopyButtons(streamingMessageDiv);
    }

    if (state.currentChatId) {
        saveChatToCache(state.currentChatId, state.chatHistory);
        api.saveChat(state.currentChatId, state.chatHistory)
            .then(() => markCacheSynced(state.currentChatId));
    }

    streamingMessageDiv = null;
    streamingContent = '';
    state.streamingMessageDiv = null;
    const providerSelect = DOM.get('providerSelectHeader');
    if (providerSelect) providerSelect.disabled = false;
    hideStopButton();
}

function showStopButton() {
    const stopBtn = DOM.get('stopBtn');
    const sendBtn = DOM.get('sendBtn');
    if (stopBtn) stopBtn.style.display = 'flex';
    if (sendBtn) sendBtn.style.display = 'none';
}

function hideStopButton() {
    const stopBtn = DOM.get('stopBtn');
    const sendBtn = DOM.get('sendBtn');
    if (stopBtn) stopBtn.style.display = 'none';
    if (sendBtn) sendBtn.style.display = 'flex';
}

export async function sendMessage() {
    const input = DOM.get('messageInput');
    const message = input?.value.trim();

    if (!message || state.isProcessing) return;

    if (getActiveRequestCount() >= CONSTANTS.MAX_CONCURRENT_REQUESTS) {
        showNotification(`Max ${CONSTANTS.MAX_CONCURRENT_REQUESTS} concurrent requests reached`);
        return;
    }

    if (!state.currentChatId) {
        try {
            const newChat = await api.createChat(state.currentWorkspace);
            state.currentChatId = newChat.id;
            localStorage.setItem('currentChatId', state.currentChatId);
            loadChatList();
        } catch (error) {
            showNotification('Failed to create chat');
            return;
        }
    }

    state.currentRequestId++;
    const thisRequestId = state.currentRequestId;
    const thisChatId = state.currentChatId;

    const imagesToSend = [...state.selectedImages];
    const hasImages = imagesToSend.length > 0;
    const formattedMessage = formatMessageWithImages(message, imagesToSend);

    const displayMessage = hasImages
        ? `📷 [${imagesToSend.length} image${imagesToSend.length > 1 ? 's' : ''}] ${message}`
        : message;

    input.value = '';
    autoResize(input);
    clearSelectedImages();
    hideWelcome();
    addMessage('user', displayMessage, true);
    showTypingIndicator('Connecting...');
    showStopButton();
    state.isProcessing = true;
    DOM.get('sendBtn').disabled = true;

    state.currentAbortController = new AbortController();
    const activeRequest = createActiveRequest(thisChatId, state.currentAbortController, thisRequestId);

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: formattedMessage,
                workspace: state.currentWorkspace,
                chatId: state.currentChatId,
                history: state.chatHistory || []
            }),
            signal: state.currentAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamingCompleted = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                const isBackground = thisChatId !== state.currentChatId;
                const bgRequest = activeRequests.get(thisChatId);

                try {
                    const data = JSON.parse(line.slice(6));

                    switch (data.type) {
                        case 'status':
                            if (bgRequest) bgRequest.status = data.message;
                            if (!isBackground) updateTypingStatus(data.message);
                            break;

                        case 'stream_start':
                            if (bgRequest) bgRequest.status = 'streaming';
                            if (!isBackground) startStreamingMessage(thisRequestId);
                            break;

                        case 'stream':
                            if (bgRequest) bgRequest.streamingContent += data.content;
                            if (!isBackground) appendStreamingContent(data.content, thisRequestId);
                            break;

                        case 'stream_end':
                            const finalContent = isBackground
                                ? bgRequest?.streamingContent
                                : (streamingContent || data.content);

                            if (isBackground) {
                                completeActiveRequest(thisChatId, finalContent, true);
                            } else {
                                finalizeStreamingMessage(finalContent, thisRequestId);
                                completeActiveRequest(thisChatId, finalContent, false);
                                hideTypingIndicator();
                            }
                            streamingCompleted = true;
                            break;

                        case 'response':
                            if (!streamingCompleted) {
                                if (isBackground) {
                                    completeActiveRequest(thisChatId, data.message, true);
                                } else {
                                    hideTypingIndicator();
                                    addMessage('assistant', data.message);
                                    completeActiveRequest(thisChatId, data.message, false);
                                }
                            }
                            break;

                        case 'aborted':
                            if (!isBackground && streamingContent) {
                                const partialContent = streamingContent + '\n\n*(stopped)*';
                                finalizeStreamingMessage(partialContent, thisRequestId);
                                completeActiveRequest(thisChatId, partialContent, false);
                            }
                            activeRequests.delete(thisChatId);
                            hideTypingIndicator();
                            hideStopButton();
                            break;

                        case 'error':
                            activeRequests.delete(thisChatId);
                            if (!isBackground) {
                                hideTypingIndicator();
                                addMessage('assistant', `❌ Error: ${data.message}`, true);
                            }
                            break;

                        case 'done':
                            if (!isBackground) {
                                hideTypingIndicator();
                                state.isProcessing = false;
                                DOM.get('sendBtn').disabled = false;
                            }
                            break;
                    }
                } catch (e) {
                    console.error('[SSE] Parse error:', e);
                }
            }
        }
    } catch (error) {
        if (error.name !== 'AbortError') {
            console.error('[STREAM] Error:', error);
            showNotification('Connection error', 'error');
        }
        activeRequests.delete(thisChatId);
        hideTypingIndicator();
    } finally {
        state.isProcessing = false;
        DOM.get('sendBtn').disabled = false;
    }
}

export function stopCurrentRequest() {
    if (state.currentAbortController) {
        state.currentAbortController.abort();
        state.currentAbortController = null;
        fetch('/api/chat/abort', { method: 'POST' }).catch(() => {});
    }
    hideTypingIndicator();
    hideStopButton();
    state.isProcessing = false;
    DOM.get('sendBtn').disabled = false;
}

window.sendMessage = sendMessage;
window.stopStreaming = stopCurrentRequest;

