import { state, CONSTANTS } from './state.js';
import { DOM, autoResize, escapeHtml } from './dom.js';
import { api } from './api.js';
import { getUnsyncedChats, saveChatToCache } from './cache.js';
import { showNotification, toggleSettings, toggleSidebar, toggleDevTools } from './ui.js';
import { handleImageSelect, toggleVoiceRecording } from './media.js';
import { loadReminders, addReminder } from './reminders.js';
import { loadChat, loadChatList, newChat, renderChatMessages, clearAllChats } from './chat.js';
import { sendMessage, stopCurrentRequest } from './streaming.js';

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
}

async function initApp() {
    console.log('[APP] Initializing AI Chat App...');

    // Restore theme from localStorage immediately
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        applyTheme(savedTheme);
    }

    // Make chat container visible (hidden initially to prevent flash)
    const chatMessagesContainer = DOM.get('chatMessages');
    if (chatMessagesContainer) {
        chatMessagesContainer.style.visibility = 'visible';
    }

    try {
        const settings = await api.getSettings();
        if (settings && !settings.error) {
            state.currentWorkspace = settings.workspace || '';
            const workspaceInput = DOM.get('workspacePath');
            if (workspaceInput) {
                workspaceInput.value = state.currentWorkspace;
            }
            updateWorkspaceDisplay();

            if (settings.model) {
                state.currentModel = settings.model;
            }
            if (settings.available_models) {
                state.availableModels = settings.available_models;
                populateModelSelect();
            }
        }
    } catch (error) {
        console.error('[APP] Failed to load settings:', error);
    }

    await loadReminders();
    await loadChatList();

    const lastChatId = localStorage.getItem('currentChatId');
    if (lastChatId) {
        await loadChat(lastChatId);
    }

    syncOfflineChats();
    setupEventListeners();

    console.log('[APP] Initialization complete');
}

async function syncOfflineChats() {
    const unsyncedChats = getUnsyncedChats();
    for (const chatId of unsyncedChats) {
        try {
            const cached = localStorage.getItem(`${CONSTANTS.CACHE_PREFIX}${chatId}`);
            if (cached) {
                const data = JSON.parse(cached);
                if (data.messages) {
                    await api.saveChat(chatId, data.messages);
                    data.synced = true;
                    localStorage.setItem(`${CONSTANTS.CACHE_PREFIX}${chatId}`, JSON.stringify(data));
                }
            }
        } catch (error) {
            console.error(`[APP] Failed to sync chat ${chatId}:`, error);
        }
    }
}

function setupEventListeners() {
    const messageInput = DOM.get('messageInput');
    if (messageInput) {
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        messageInput.addEventListener('input', () => autoResize(messageInput));
    }

    const sendBtn = DOM.get('sendBtn');
    if (sendBtn) {
        sendBtn.onclick = sendMessage;
    }

    const newChatBtn = DOM.get('newChatBtn');
    if (newChatBtn) {
        newChatBtn.onclick = newChat;
    }

    const settingsBtn = DOM.get('settingsBtn');
    if (settingsBtn) {
        settingsBtn.onclick = toggleSettings;
    }

    const sidebarToggle = DOM.get('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.onclick = toggleSidebar;
    }

    const imageBtn = DOM.get('imageBtn');
    if (imageBtn) {
        imageBtn.onclick = handleImageSelect;
    }

    const voiceBtn = DOM.get('voiceBtn');
    if (voiceBtn) {
        voiceBtn.onclick = toggleVoiceRecording;
    }

    const stopBtn = DOM.get('stopBtn');
    if (stopBtn) {
        stopBtn.onclick = stopCurrentRequest;
    }

    const saveSettingsBtn = DOM.get('saveSettingsBtn');
    if (saveSettingsBtn) {
        saveSettingsBtn.onclick = saveSettings;
    }

    const selectFolderBtn = DOM.get('selectFolderBtn');
    if (selectFolderBtn && window.electronAPI?.selectFolder) {
        selectFolderBtn.onclick = selectWorkspaceFolder;
    }

    const addReminderBtn = DOM.get('addReminderBtn');
    if (addReminderBtn) {
        addReminderBtn.onclick = addReminder;
    }

    const settingsModal = DOM.get('settingsModal');
    if (settingsModal) {
        settingsModal.onclick = (e) => {
            if (e.target === settingsModal) {
                toggleSettings();
            }
        };
    }

    const browserModal = DOM.get('browserModal');
    if (browserModal) {
        browserModal.onclick = (e) => {
            if (e.target === browserModal) {
                closeBrowser();
            }
        };
    }

    const devToolsModal = DOM.get('devToolsModal');
    if (devToolsModal) {
        devToolsModal.onclick = (e) => {
            if (e.target === devToolsModal) {
                toggleDevTools();
            }
        };
    }
}

async function saveSettings() {
    const workspaceInput = DOM.get('workspacePath');
    const workspace = workspaceInput?.value.trim() || '';

    try {
        await api.saveSettings({ workspace });
        state.currentWorkspace = workspace;
        showNotification('Settings saved!');
        toggleSettings();
    } catch (error) {
        showNotification('Failed to save settings', 'error');
    }
}

async function selectWorkspaceFolder() {
    if (!window.electronAPI?.selectFolder) return;

    try {
        const result = await window.electronAPI.selectFolder();
        if (!result.canceled && result.filePaths.length > 0) {
            const workspaceInput = DOM.get('workspacePath');
            if (workspaceInput) {
                workspaceInput.value = result.filePaths[0];
            }
        }
    } catch (error) {
        console.error('[APP] Failed to select folder:', error);
    }
}

function browseWorkspace() {
    const modal = DOM.get('browserModal');
    if (!modal) {
        console.error('browserModal not found');
        return;
    }
    if (modal.classList.contains('active')) {
        modal.classList.remove('active');
        return;
    }
    state.browserCurrentPath = state.currentWorkspace || '~';
    const pathEl = DOM.get('browserPath');
    const listEl = DOM.get('browserList');
    if (pathEl) pathEl.textContent = state.browserCurrentPath;
    if (listEl) listEl.innerHTML = '';
    modal.classList.add('active');
    loadBrowserDirectory(state.browserCurrentPath);
}

function closeBrowser() {
    const modal = DOM.get('browserModal');
    if (modal) modal.classList.remove('active');
}

function navigateToHome() {
    loadBrowserDirectory('~');
}

function updateWorkspaceDisplay() {
    const display = DOM.get('workspaceDisplay');
    const input = DOM.get('workspaceInput');
    const current = DOM.get('currentWorkspace');

    let displayPath = state.currentWorkspace;
    if (displayPath && displayPath !== '~') {
        const folderName = displayPath.split('/').filter(p => p).pop() || displayPath;
        displayPath = folderName;
    }

    if (display) display.textContent = displayPath || '~/';
    if (input) input.value = state.currentWorkspace;
    if (current) current.innerHTML = `<i class="fas fa-folder-open"></i> Current: ${state.currentWorkspace}`;
}

async function selectCurrentDir() {
    const workspaceInput = DOM.get('workspaceInput') || DOM.get('workspacePath');
    if (workspaceInput) workspaceInput.value = state.browserCurrentPath;
    state.currentWorkspace = state.browserCurrentPath;
    closeBrowser();
    updateWorkspaceDisplay();

    try {
        await api.saveSettings({ workspace: state.currentWorkspace });
        localStorage.setItem('workspace', state.currentWorkspace);
        showNotification('Workspace changed');
    } catch (error) {
        console.error('Error saving workspace:', error);
    }
}

async function loadBrowserDirectory(path) {
    const listEl = DOM.get('browserList');
    const pathEl = DOM.get('browserPath');

    if (!listEl) return;

    listEl.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (data.error) {
            listEl.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        state.browserCurrentPath = data.path || path;
        if (pathEl) pathEl.textContent = state.browserCurrentPath;

        const items = data.items || [];
        if (items.length === 0) {
            listEl.innerHTML = '<div class="empty">Empty directory</div>';
            return;
        }

        listEl.innerHTML = items.map(item => `
            <div class="browser-item ${item.type}" onclick="window.browseItem('${escapeHtml(item.path)}', '${item.type}')">
                <i class="fas fa-${item.type === 'directory' ? 'folder' : 'file'}"></i>
                <span>${escapeHtml(item.name)}</span>
            </div>
        `).join('');
    } catch (error) {
        listEl.innerHTML = `<div class="error">Failed to load directory</div>`;
        console.error('Error loading directory:', error);
    }
}

function browseItem(path, type) {
    if (type === 'directory') {
        loadBrowserDirectory(path);
    }
}

function populateModelSelect() {
    const select = DOM.get('modelSelect');
    const headerSelect = DOM.get('modelSelectHeader');

    [select, headerSelect].forEach(sel => {
        if (!sel) return;
        sel.innerHTML = '';
        state.availableModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === state.currentModel) {
                option.selected = true;
            }
            sel.appendChild(option);
        });
    });
}

async function updateModelFromHeader() {
    const headerSelect = DOM.get('modelSelectHeader');
    const modalSelect = DOM.get('modelSelect');
    if (!headerSelect) return;

    const model = headerSelect.value;

    if (state.currentAIProvider === 'openai') {
        state.currentOpenAIModel = model;
        localStorage.setItem('currentOpenAIModel', model);
    } else if (state.currentAIProvider === 'codex') {
        state.currentCodexModel = model;
        localStorage.setItem('currentCodexModel', model);
    } else {
        state.currentModel = model;
        if (modalSelect) {
            modalSelect.value = model;
        }
    }

    try {
        await api.saveSettings({ model: model });
        console.log('[APP] Model updated to:', model, 'for provider:', state.currentAIProvider);
    } catch (error) {
        console.error('Failed to update model:', error);
    }
}

async function updateProviderFromHeader() {
    const headerSelect = DOM.get('providerSelectHeader');
    if (!headerSelect) return;

    if (state.streamingMessageDiv) {
        showNotification('Cannot switch provider while chat is streaming', 'warning');
        headerSelect.value = state.currentAIProvider || 'auggie';
        return;
    }

    if (state.chatHistory && state.chatHistory.length > 0) {
        console.log('[APP] Blocking provider switch - chat has messages:', state.chatHistory.length);
        showNotification('Cannot switch provider mid-chat. Start a new chat to change provider.', 'warning');
        headerSelect.value = state.currentAIProvider || 'auggie';
        return;
    }

    const provider = headerSelect.value;
    state.currentAIProvider = provider;
    localStorage.setItem('currentAIProvider', provider);

    updateModelSelectVisibility();

    try {
        await api.saveSettings({ ai_provider: provider });
        console.log('[APP] Provider updated to:', provider);
        const providerNames = { auggie: 'Auggie', codex: 'Codex', openai: 'OpenAI' };
        showNotification(`Switched to ${providerNames[provider] || provider}`);
    } catch (error) {
        console.error('Failed to update provider:', error);
    }
}

function updateModelSelectVisibility() {
    const modelSelectHeader = DOM.get('modelSelectHeader');
    if (!modelSelectHeader) return;

    if (state.currentAIProvider === 'openai') {
        modelSelectHeader.innerHTML = '';
        const openaiModels = state.availableOpenAIModels || ['gpt-5.2', 'gpt-5.2-chat-latest', 'gpt-5.1', 'gpt-5-mini', 'gpt-5-nano'];
        openaiModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === state.currentOpenAIModel) {
                option.selected = true;
            }
            modelSelectHeader.appendChild(option);
        });
    } else if (state.currentAIProvider === 'codex') {
        modelSelectHeader.innerHTML = '';
        const codexModels = state.availableCodexModels || ['gpt-5.2', 'gpt-5.1', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5.2-chat-latest'];
        codexModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === (state.currentCodexModel || 'gpt-5.2')) {
                option.selected = true;
            }
            modelSelectHeader.appendChild(option);
        });
    } else {
        populateModelSelect();
    }
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

window.appState = state;
window.toggleSettings = toggleSettings;
window.toggleSidebar = toggleSidebar;
window.browseWorkspace = browseWorkspace;
window.closeBrowser = closeBrowser;
window.navigateToHome = navigateToHome;
window.selectCurrentDir = selectCurrentDir;
window.browseItem = browseItem;
window.updateModelFromHeader = updateModelFromHeader;
window.updateProviderFromHeader = updateProviderFromHeader;
window.handleKeyDown = handleKeyDown;
window.autoResize = autoResize;
window.sendMessage = sendMessage;

let editingShortcutIndex = null;

function toggleAddShortcutModal(editIndex = null) {
    const modal = document.getElementById('addShortcutModal');
    const modalTitle = modal.querySelector('.modal-header h2');
    const saveBtn = modal.querySelector('.save-shortcut-btn');

    modal.classList.toggle('active');

    if (modal.classList.contains('active')) {
        editingShortcutIndex = editIndex;

        if (editIndex !== null) {
            const shortcuts = JSON.parse(localStorage.getItem('customShortcuts') || '[]');
            const shortcut = shortcuts[editIndex];
            document.getElementById('shortcutLabel').value = shortcut.label;
            document.getElementById('shortcutPrompt').value = shortcut.prompt;
            modalTitle.textContent = 'Edit Shortcut';
            saveBtn.textContent = 'Update';
        } else {
            document.getElementById('shortcutLabel').value = '';
            document.getElementById('shortcutPrompt').value = '';
            modalTitle.textContent = 'Add Shortcut';
            saveBtn.textContent = 'Save';
        }
        document.getElementById('shortcutLabel').focus();
    } else {
        editingShortcutIndex = null;
    }
}

function saveShortcut() {
    const label = document.getElementById('shortcutLabel').value.trim();
    const prompt = document.getElementById('shortcutPrompt').value.trim();

    if (!label && !prompt) {
        showNotification('Please fill in at least one field', 'error');
        return;
    }

    const finalLabel = label || prompt.split(/\s+/)[0];
    const finalPrompt = prompt || label;

    const shortcuts = JSON.parse(localStorage.getItem('customShortcuts') || '[]');

    if (editingShortcutIndex !== null) {
        shortcuts[editingShortcutIndex] = { label: finalLabel, prompt: finalPrompt };
        showNotification('Shortcut updated');
    } else {
        shortcuts.push({ label: finalLabel, prompt: finalPrompt });
        showNotification('Shortcut added');
    }

    localStorage.setItem('customShortcuts', JSON.stringify(shortcuts));
    renderCustomShortcuts();
    toggleAddShortcutModal();
}

function initDefaultShortcuts() {
    const existing = localStorage.getItem('customShortcuts');
    if (!existing) {
        const defaults = [
            { label: 'commit', prompt: 'commit the changes with small message' },
            { label: 'yes', prompt: 'yes' }
        ];
        localStorage.setItem('customShortcuts', JSON.stringify(defaults));
    }
}

let draggedShortcutIndex = null;

function renderCustomShortcuts() {
    const container = document.querySelector('.input-quick-shortcuts');
    if (!container) return;

    container.querySelectorAll('.custom-shortcut').forEach(el => el.remove());

    const shortcuts = JSON.parse(localStorage.getItem('customShortcuts') || '[]');
    shortcuts.forEach((shortcut, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'shortcut-btn custom-shortcut';
        wrapper.title = shortcut.prompt;
        wrapper.draggable = true;
        wrapper.dataset.index = index;

        wrapper.addEventListener('dragstart', (e) => {
            draggedShortcutIndex = index;
            wrapper.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        wrapper.addEventListener('dragend', () => {
            wrapper.classList.remove('dragging');
            draggedShortcutIndex = null;
        });

        wrapper.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'move';
            if (draggedShortcutIndex !== null && draggedShortcutIndex !== index) {
                wrapper.classList.add('drag-over');
            }
        });

        wrapper.addEventListener('dragleave', (e) => {
            wrapper.classList.remove('drag-over');
        });

        wrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            wrapper.classList.remove('drag-over');
            if (draggedShortcutIndex !== null && draggedShortcutIndex !== index) {
                reorderShortcuts(draggedShortcutIndex, index);
            }
        });

        const label = document.createElement('span');
        label.className = 'shortcut-label';
        label.textContent = shortcut.label;
        label.onclick = () => window.sendSuggestion(shortcut.prompt);

        const actions = document.createElement('span');
        actions.className = 'shortcut-actions';

        const editBtn = document.createElement('span');
        editBtn.className = 'shortcut-edit';
        editBtn.innerHTML = '<i class="fas fa-pen"></i>';
        editBtn.onclick = (e) => {
            e.stopPropagation();
            toggleAddShortcutModal(index);
        };

        const deleteBtn = document.createElement('span');
        deleteBtn.className = 'shortcut-delete';
        deleteBtn.innerHTML = '&times;';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            deleteShortcut(index);
        };

        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);
        wrapper.appendChild(label);
        wrapper.appendChild(actions);
        container.appendChild(wrapper);
    });
}

function reorderShortcuts(fromIndex, toIndex) {
    const shortcuts = JSON.parse(localStorage.getItem('customShortcuts') || '[]');
    const [moved] = shortcuts.splice(fromIndex, 1);
    shortcuts.splice(toIndex, 0, moved);
    localStorage.setItem('customShortcuts', JSON.stringify(shortcuts));
    renderCustomShortcuts();
}

function deleteShortcut(index) {
    const shortcuts = JSON.parse(localStorage.getItem('customShortcuts') || '[]');
    shortcuts.splice(index, 1);
    localStorage.setItem('customShortcuts', JSON.stringify(shortcuts));
    renderCustomShortcuts();
    showNotification('Shortcut deleted');
}

window.toggleAddShortcutModal = toggleAddShortcutModal;
window.saveShortcut = saveShortcut;
window.renderCustomShortcuts = renderCustomShortcuts;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
    initDefaultShortcuts();
    renderCustomShortcuts();
    document.getElementById('addShortcutBtn')?.addEventListener('click', toggleAddShortcutModal);

    document.getElementById('addShortcutModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'addShortcutModal') {
            toggleAddShortcutModal();
        }
    });
});

