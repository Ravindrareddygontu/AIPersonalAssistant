import { state, activeRequests } from './state.js';
import { DOM, escapeHtml, scrollToBottom } from './dom.js';
import { api } from './api.js';
import { saveChatToCache, loadChatFromCache, markCacheSynced } from './cache.js';
import { formatMessage, addCodeCopyButtons } from './markdown.js';
import { showNotification } from './ui.js';

function showConfirmDialog(message) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('confirmDialog');
        const messageEl = document.getElementById('confirmMessage');
        const cancelBtn = document.getElementById('confirmCancel');
        const deleteBtn = document.getElementById('confirmDelete');

        if (!dialog || !messageEl || !cancelBtn || !deleteBtn) {
            resolve(confirm(message));
            return;
        }

        messageEl.textContent = message;
        dialog.classList.add('show');

        const cleanup = () => {
            dialog.classList.remove('show');
            cancelBtn.onclick = null;
            deleteBtn.onclick = null;
            dialog.onclick = null;
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        deleteBtn.onclick = () => {
            cleanup();
            resolve(true);
        };

        dialog.onclick = (e) => {
            if (e.target === dialog) {
                cleanup();
                resolve(false);
            }
        };
    });
}

export const WELCOME_HTML = `
    <div class="welcome-message">
        <h2>Hello, what do you want?</h2>
        <div class="quick-actions">
            <button class="action-btn" onclick="window.sendSuggestion('Show me the folder structure of this project with main files and their purposes')">
                <i class="fas fa-sitemap"></i>
                <span>Project structure</span>
            </button>
            <button class="action-btn" onclick="window.sendSuggestion('List all files in the current directory and briefly describe what each one does')">
                <i class="fas fa-folder-tree"></i>
                <span>List files</span>
            </button>
            <button class="action-btn" onclick="window.sendSuggestion('Check if any application is running on port 5000 and show me the process details')">
                <i class="fas fa-server"></i>
                <span>Check port</span>
            </button>
            <button class="action-btn" onclick="window.sendSuggestion('What are the latest AI news and developments today?')">
                <i class="fas fa-newspaper"></i>
                <span>AI news today</span>
            </button>
            <button class="action-btn" onclick="window.sendSuggestion('Find all TODO comments in this project and list them with their file locations')">
                <i class="fas fa-clipboard-list"></i>
                <span>Find TODOs</span>
            </button>
            <button class="action-btn" onclick="window.sendSuggestion('Show me the git status and recent commits in this repository')">
                <i class="fas fa-code-branch"></i>
                <span>Git status</span>
            </button>
        </div>
    </div>
`;

export function generateMessageId(chatId, index, content) {
    const uniqueSuffix = crypto.randomUUID
        ? crypto.randomUUID().substring(0, 8)
        : Math.random().toString(16).substring(2, 10);
    return `${chatId}-${index}-${uniqueSuffix}`;
}

export function renderChatMessages(messages) {
    if (state.isProcessing) {
        console.log('[RENDER] Skipping render, message is being processed');
        return;
    }

    const container = DOM.get('chatMessages');
    if (!container) return;

    container.innerHTML = '';

    if (!messages || messages.length === 0) {
        container.innerHTML = WELCOME_HTML;
        return;
    }

    messages.forEach((msg, idx) => {
        if (!msg.messageId) {
            msg.messageId = generateMessageId(state.currentChatId, idx, msg.content);
        }
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role}`;
        messageDiv.dataset.messageId = msg.messageId;
        messageDiv.innerHTML = createMessageHTML(msg.role, msg.content, idx, msg.messageId);
        container.appendChild(messageDiv);
        addCodeCopyButtons(messageDiv);
    });

    scrollToBottom(container);
}

export function createMessageHTML(role, content, index, messageId) {
    const msgId = messageId || generateMessageId(state.currentChatId, index, content);

    if (role === 'assistant') {
        return `<div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-content">
                <div class="message-actions">
                    <button class="copy-btn" data-content="${encodeURIComponent(content)}">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
                <div class="message-text">${formatMessage(content)}</div>
            </div>`;
    } else {
        const encodedContent = btoa(unescape(encodeURIComponent(content)));
        const plainContent = escapeHtml(content).replace(/\n/g, '<br>');
        return `<div class="message-avatar"><i class="fas fa-user"></i></div>
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

const COPY_FEEDBACK_DURATION = 2000;

function showCopyFeedback(btn) {
    const icon = btn.querySelector('i');
    if (icon) {
        icon.className = 'fas fa-check';
        btn.classList.add('copied');
        setTimeout(() => {
            icon.className = 'fas fa-copy';
            btn.classList.remove('copied');
        }, COPY_FEEDBACK_DURATION);
    }
}

function copyToClipboard(text, btn, errorMsg = 'Failed to copy') {
    navigator.clipboard.writeText(text)
        .then(() => showCopyFeedback(btn))
        .catch(err => console.error(errorMsg + ':', err));
}

export function copyMessage(btn) {
    const encodedContent = btn.getAttribute('data-content');
    if (!encodedContent) return;

    const content = decodeURIComponent(encodedContent);
    navigator.clipboard.writeText(content).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
            btn.classList.remove('copied');
        }, COPY_FEEDBACK_DURATION);
    });
}

export function copyUserMessage(btn) {
    const encodedContent = btn.getAttribute('data-content');
    if (!encodedContent) return;

    const content = decodeURIComponent(escape(atob(encodedContent)));
    copyToClipboard(content, btn, 'Failed to copy message');
}

export function editMessage(btn, messageIndex, encodedContent, messageId = null) {
    if (state.isProcessing) {
        return;
    }

    const content = decodeURIComponent(encodedContent);
    const container = document.getElementById('chatMessages');
    const messages = container.querySelectorAll('.message');

    let userMessageEl = btn.closest('.message');

    if (messageId) {
        const matchingEl = container.querySelector(`[data-message-id="${messageId}"]`);
        if (matchingEl) {
            userMessageEl = matchingEl;
        }

        const historyIdx = state.chatHistory.findIndex(msg => msg.messageId === messageId);
        if (historyIdx !== -1) {
            messageIndex = historyIdx;
        }
    }

    console.log(`[EDIT] Starting inline edit at index ${messageIndex}, messageId: ${messageId}`);

    const originalContent = content;
    const originalHTML = userMessageEl.innerHTML;

    const contentDiv = userMessageEl.querySelector('.message-content');
    const actionsOutside = userMessageEl.querySelector('.message-actions-outside');
    const textDiv = contentDiv.querySelector('.message-text');

    const originalContentWidth = contentDiv.offsetWidth;
    const originalTextHeight = textDiv.offsetHeight;

    if (actionsOutside) actionsOutside.style.display = 'none';
    userMessageEl.classList.add('editing');

    const originalTextHTML = textDiv.innerHTML;

    textDiv.innerHTML = `
        <textarea class="edit-textarea">${escapeHtml(content)}</textarea>
        <div class="edit-buttons">
            <button class="edit-cancel-btn" title="Cancel (Esc)">Cancel</button>
            <button class="edit-submit-btn" title="Submit (Enter)">Submit</button>
        </div>
    `;

    const textarea = textDiv.querySelector('.edit-textarea');
    const submitBtn = textDiv.querySelector('.edit-submit-btn');
    const cancelBtn = textDiv.querySelector('.edit-cancel-btn');

    const minWidth = Math.max(originalContentWidth, 280);
    textarea.style.width = minWidth + 'px';
    contentDiv.style.minWidth = minWidth + 'px';

    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
    const initialHeight = textarea.scrollHeight;

    const autoResizeTextarea = () => {
        textarea.style.height = 'auto';
        const newHeight = Math.min(Math.max(textarea.scrollHeight, initialHeight), 200);
        textarea.style.height = newHeight + 'px';
    };

    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    textarea.addEventListener('input', autoResizeTextarea);

    cancelBtn.onclick = () => {
        console.log(`[EDIT] Cancelled edit at index ${messageIndex}`);
        textDiv.innerHTML = originalTextHTML;
        userMessageEl.classList.remove('editing');
        if (actionsOutside) actionsOutside.style.display = '';
    };

    submitBtn.onclick = async () => {
        const newContent = textarea.value.trim();
        if (!newContent) {
            showNotification('Message cannot be empty');
            return;
        }

        console.log(`[EDIT] Submitting edit at messageIndex=${messageIndex}, messageId=${messageId}`);

        if (state.currentAbortController) {
            console.log(`[EDIT] Aborting existing stream before edit`);
            state.currentAbortController.abort();
            state.currentAbortController = null;
            fetch('/api/chat/abort', { method: 'POST' }).catch(() => {});
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        state.isProcessing = false;

        const chatContainer = document.getElementById('chatMessages');

        let targetMessageEl = null;
        if (messageId) {
            targetMessageEl = chatContainer.querySelector(`[data-message-id="${messageId}"]`);
        }
        if (!targetMessageEl) {
            targetMessageEl = userMessageEl;
        }

        if (!targetMessageEl) {
            console.error('[EDIT] Could not find target message element!');
            return;
        }

        const allChildren = Array.from(chatContainer.children);
        const targetIndex = allChildren.indexOf(targetMessageEl);

        if (targetIndex === -1) {
            chatContainer.innerHTML = '';
        } else {
            for (let i = allChildren.length - 1; i >= targetIndex; i--) {
                allChildren[i].remove();
            }
        }

        state.chatHistory = state.chatHistory.slice(0, messageIndex);
        console.log(`[EDIT] Chat history truncated to ${state.chatHistory.length} messages`);

        await api.saveChat(state.currentChatId, state.chatHistory);
        console.log(`[EDIT] DB updated with truncated history`);

        if (state.chatHistory.length === 0 && chatContainer.children.length === 0) {
            chatContainer.innerHTML = WELCOME_HTML;
        }

        const input = document.getElementById('messageInput');
        input.value = newContent;
        console.log(`[EDIT] Calling sendMessage() now...`);
        if (window.sendMessage) window.sendMessage();
    };

    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            cancelBtn.click();
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitBtn.click();
        }
    });
}

export function addMessage(role, content, skipSave = false) {
    const index = state.chatHistory.length;
    const messageId = generateMessageId(state.currentChatId, index, content);

    state.chatHistory.push({ role, content, messageId });

    const container = DOM.get('chatMessages');
    if (container) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.dataset.messageId = messageId;
        messageDiv.innerHTML = createMessageHTML(role, content, index, messageId);
        container.appendChild(messageDiv);
        addCodeCopyButtons(messageDiv);
        scrollToBottom(container);
    }

    if (!skipSave && state.currentChatId) {
        saveChatToCache(state.currentChatId, state.chatHistory);
        api.saveChat(state.currentChatId, state.chatHistory)
            .then(() => markCacheSynced(state.currentChatId))
            .catch(err => console.error('Failed to save message:', err));
    }
}

export async function newChat() {
    state.currentChatId = null;
    state.chatHistory = [];
    localStorage.removeItem('currentChatId');

    const container = DOM.get('chatMessages');
    if (container) {
        container.innerHTML = WELCOME_HTML;
    }

    document.querySelectorAll('.chat-history-item').forEach(item => {
        item.classList.remove('active');
    });
}

export async function loadChat(chatId) {
    try {
        const cached = loadChatFromCache(chatId);
        if (cached && cached.messages) {
            state.currentChatId = chatId;
            state.chatHistory = cached.messages;
            localStorage.setItem('currentChatId', chatId);
            renderChatMessages(state.chatHistory);
        }

        const chat = await api.getChat(chatId);
        if (chat && !chat.error) {
            state.currentChatId = chatId;
            state.chatHistory = chat.messages || [];
            localStorage.setItem('currentChatId', chatId);
            renderChatMessages(state.chatHistory);
            saveChatToCache(chatId, state.chatHistory);
            updateActiveChat(chatId);

            if (chat.provider) {
                state.currentAIProvider = chat.provider;
                localStorage.setItem('currentAIProvider', chat.provider);
                const providerSelect = document.getElementById('providerSelectHeader');
                if (providerSelect) {
                    providerSelect.value = chat.provider;
                }
                if (window.updateModelSelectVisibility) {
                    window.updateModelSelectVisibility();
                }
            }
        }
    } catch (error) {
        console.error('Failed to load chat:', error);
    }
}

export async function deleteChat(chatId, event) {
    if (event) event.stopPropagation();

    const confirmed = await showConfirmDialog('Delete this conversation?');
    if (!confirmed) return;

    try {
        await api.deleteChat(chatId);

        if (state.currentChatId === chatId) {
            await newChat();
        }

        await loadChatList();
    } catch (error) {
        console.error('Failed to delete chat:', error);
    }
}

function updateActiveChat(chatId) {
    document.querySelectorAll('.chat-history-item').forEach(item => {
        item.classList.toggle('active', item.dataset?.chatId === chatId);
    });
}

export async function loadChatList() {
    try {
        const chats = await api.getChats();
        renderChatList(chats);
        return chats;
    } catch (error) {
        console.error('Failed to load chats:', error);
        return [];
    }
}

export function renderChatList(chats) {
    const container = DOM.get('chatHistory');
    if (!container) return;

    container.innerHTML = '';

    if (!chats || chats.length === 0) {
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
        const isActive = chat.id === state.currentChatId;
        const hasBgRequest = activeRequests.has(chat.id);

        item.className = `chat-history-item ${isActive ? 'active' : ''} ${hasBgRequest ? 'has-background-request' : ''}`;
        item.dataset.chatId = chat.id;
        item.onclick = (e) => {
            if (!e.target.closest('.delete-chat-btn')) {
                loadChat(chat.id);
            }
        };

        const date = new Date(chat.updated_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        item.innerHTML = `
            <span class="chat-title">${escapeHtml(chat.title)}</span>
            <button class="delete-chat-btn" onclick="window.deleteChat('${chat.id}', event)" title="Delete">
                <i class="fas fa-trash"></i>
            </button>
        `;

        container.appendChild(item);
    });
}

export function hideWelcome() {
    const welcome = document.querySelector('.welcome-message');
    if (welcome) welcome.remove();
}

export async function createNewChat() {
    if (state.chatHistory.length === 0 && state.currentChatId) {
        console.log('[NEW CHAT] Already in empty chat, skipping creation');
        return;
    }

    try {
        await api.resetSession(state.currentWorkspace);
        console.log('[NEW CHAT] Auggie session reset');

        const newChatData = await api.createChat(state.currentWorkspace);
        state.currentChatId = newChatData.id;
        state.chatHistory = [];
        localStorage.setItem('currentChatId', state.currentChatId);

        if (newChatData.provider) {
            state.currentAIProvider = newChatData.provider;
            localStorage.setItem('currentAIProvider', newChatData.provider);
            const providerSelect = document.getElementById('providerSelectHeader');
            if (providerSelect) {
                providerSelect.value = newChatData.provider;
            }
            if (window.updateModelSelectVisibility) {
                window.updateModelSelectVisibility();
            }
        }

        const container = DOM.get('chatMessages');
        if (container) {
            container.innerHTML = WELCOME_HTML;
        }

        await loadChatList();
        updateActiveChat(state.currentChatId);
    } catch (error) {
        console.error('Failed to create new chat:', error);
    }
}

export async function clearAllChats() {
    const confirmed = await showConfirmDialog('Delete all chat history? This cannot be undone.');
    if (!confirmed) return;

    localStorage.removeItem('currentChatId');
    localStorage.removeItem('cachedChatList');
    state.currentChatId = null;
    state.chatHistory = [];

    const chatMessages = DOM.get('chatMessages');
    if (chatMessages) {
        chatMessages.innerHTML = `
            <div class="loading-state" style="display: flex; justify-content: center; align-items: center; height: 100%; opacity: 0.6;">
                <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: var(--text-secondary);"></i>
            </div>
        `;
    }

    const historyContainer = document.getElementById('chatHistory');
    if (historyContainer) {
        historyContainer.innerHTML = `
            <div class="chat-history-cleared" style="display: flex; flex-direction: column; align-items: center; padding: 20px; color: var(--text-muted);">
                <i class="fas fa-check-circle" style="font-size: 1.5rem; margin-bottom: 8px; color: var(--success);"></i>
                <span>All chats cleared</span>
            </div>
        `;
    }

    try {
        await fetch('/api/chats/clear', { method: 'DELETE' });
        await createNewChat();

        setTimeout(() => {
            const clearedMsg = historyContainer?.querySelector('.chat-history-cleared');
            if (clearedMsg) {
                clearedMsg.style.transition = 'opacity 0.3s ease';
                clearedMsg.style.opacity = '0';
            }
        }, 1500);
    } catch (error) {
        console.error('Failed to clear chats:', error);
        await createNewChat();
        if (chatMessages) {
            chatMessages.innerHTML = WELCOME_HTML;
        }
    }
}

window.sendSuggestion = (text) => {
    const input = DOM.get('messageInput');
    if (input) {
        input.value = text;
        if (window.sendMessage) window.sendMessage();
    }
};
window.deleteChat = deleteChat;
window.newChat = newChat;
window.createNewChat = createNewChat;
window.clearAllChats = clearAllChats;
window.copyMessage = copyMessage;
window.copyUserMessage = copyUserMessage;
window.editMessage = editMessage;

document.addEventListener('click', function(e) {
    const assistantCopyBtn = e.target.closest('.message.assistant .copy-btn');
    if (assistantCopyBtn) {
        e.preventDefault();
        e.stopPropagation();
        copyMessage(assistantCopyBtn);
        return;
    }

    const userCopyBtn = e.target.closest('.user-copy-btn');
    if (userCopyBtn) {
        e.preventDefault();
        e.stopPropagation();
        copyUserMessage(userCopyBtn);
        return;
    }

    const editBtn = e.target.closest('.edit-btn-outside');
    if (editBtn) {
        e.preventDefault();
        e.stopPropagation();
        const encodedContent = editBtn.getAttribute('data-content');
        const index = parseInt(editBtn.getAttribute('data-index'), 10);
        const msgId = editBtn.getAttribute('data-msgid');
        if (encodedContent) {
            const content = decodeURIComponent(escape(atob(encodedContent)));
            editMessage(editBtn, index, encodeURIComponent(content), msgId);
        }
        return;
    }
});

