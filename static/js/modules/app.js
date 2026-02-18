import { state, CONSTANTS } from './state.js';
import { DOM, autoResize, escapeHtml } from './dom.js';
import { api } from './api.js';
import { getUnsyncedChats, saveChatToCache } from './cache.js';
import { showNotification, toggleSettings, toggleSidebar } from './ui.js';
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
    state.currentModel = model;

    if (modalSelect) {
        modalSelect.value = model;
    }

    try {
        await api.saveSettings({ model: model });
        console.log('[APP] Model updated to:', model);
    } catch (error) {
        console.error('Failed to update model:', error);
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

document.addEventListener('DOMContentLoaded', initApp);

