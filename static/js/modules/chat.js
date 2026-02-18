import { state, activeRequests } from './state.js';
import { DOM, escapeHtml, scrollToBottom } from './dom.js';
import { api } from './api.js';
import { saveChatToCache, loadChatFromCache, markCacheSynced } from './cache.js';
import { formatMessage, addCodeCopyButtons } from './markdown.js';

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
    const formattedContent = role === 'assistant'
        ? formatMessage(content)
        : `<p>${escapeHtml(content)}</p>`;

    return `
        <div class="message-content">${formattedContent}</div>
    `;
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
        const newChatData = await api.createChat(state.currentWorkspace);
        state.currentChatId = newChatData.id;
        state.chatHistory = [];
        localStorage.setItem('currentChatId', state.currentChatId);

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

