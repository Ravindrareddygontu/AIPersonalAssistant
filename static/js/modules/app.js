import { state, CONSTANTS } from './state.js';
import { DOM, autoResize, escapeHtml } from './dom.js';
import { api } from './api.js';
import { getUnsyncedChats, saveChatToCache } from './cache.js';
import { showNotification, toggleSettings, toggleSidebar, toggleDevTools } from './ui.js';
import { handleImageSelect, toggleVoiceRecording } from './media.js';
import { loadReminders, addReminder } from './reminders.js';
import { loadChat, loadChatList, newChat, renderChatMessages, clearAllChats, createNewChat } from './chat.js';
import { sendMessage, stopCurrentRequest } from './streaming.js';
import {
    getShortcuts,
    toggleAddShortcutModal,
    saveShortcut,
    initDefaultShortcuts,
    migrateShortcutsWithIds,
    deleteShortcut,
    reorderShortcuts,
    isModalOpen
} from './shortcuts.js';
import {
    getWorkspaceSlots,
    setWorkspaceSlots,
    initWorkspaceSlots,
    saveWorkspaceToSlot,
    getNextWorkspace,
    activateSlot,
    hasActiveConversation
} from './workspace.js';
import { checkDbStatus, isDbConnected, checkDbStatusInBackground } from './db.js';

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
            initWorkspaceSlots(state.currentWorkspace);
            updateWorkspaceDisplay();

            if (settings.model) {
                state.currentModel = settings.model;
            }
            if (settings.available_models) {
                state.availableModels = settings.available_models;
                populateModelSelect();
            }

            const historyToggle = DOM.get('historyToggle');
            const historyEnabled = settings.history_enabled !== false;
            if (historyToggle) {
                historyToggle.checked = historyEnabled;
            }
            updateNewChatVisibility(historyEnabled);

            if (historyEnabled) {
                setTimeout(() => checkDbStatusInBackground(), 0);
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

    const historyToggle = DOM.get('historyToggle');
    if (historyToggle) {
        historyToggle.onchange = toggleHistoryEnabled;
    }

    const selectFolderBtn = DOM.get('selectFolderBtn');
    if (selectFolderBtn && window.electronAPI?.selectFolder) {
        selectFolderBtn.onclick = selectWorkspaceFolder;
    }

    setupBrowserListEvents();

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

function updateNewChatVisibility(historyEnabled) {
    const newChatBtn = DOM.get('newChatBtn');
    const sidebarActions = DOM.get('sidebarActions');
    const chatHistory = DOM.get('chatHistory');
    const sidebarFooter = DOM.get('sidebarFooter');

    const display = historyEnabled ? '' : 'none';

    if (newChatBtn) newChatBtn.style.display = display;
    if (sidebarActions) sidebarActions.style.display = display;
    if (chatHistory) chatHistory.style.display = display;
    if (sidebarFooter) sidebarFooter.style.display = display;
}

async function toggleHistoryEnabled() {
    const historyToggle = DOM.get('historyToggle');
    if (!historyToggle) return;

    const enabled = historyToggle.checked;
    try {
        await api.saveSettings({ history_enabled: enabled });
        updateNewChatVisibility(enabled);
        checkDbStatus({ connected: isDbConnected() }, enabled);
    } catch (error) {
        console.error('[APP] Failed to save history setting:', error);
        historyToggle.checked = !enabled;
        showNotification('Failed to save setting', 'error');
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

function navigateToParent() {
    if (!state.browserCurrentPath || state.browserCurrentPath === '~' || state.browserCurrentPath === '/') {
        return;
    }
    const parts = state.browserCurrentPath.split('/').filter(p => p);
    parts.pop();
    const parentPath = parts.length > 0 ? '/' + parts.join('/') : '/';
    loadBrowserDirectory(parentPath);
}

function updateWorkspaceDisplay() {
    const display = DOM.get('workspaceDisplay');
    const input = DOM.get('workspaceInput');
    const current = DOM.get('currentWorkspace');

    let displayPath = state.currentWorkspace;
    if (displayPath && displayPath !== '~') {
        const parts = displayPath.split('/').filter(p => p);
        displayPath = parts.slice(-2).join('/') || displayPath;
    }

    if (display) display.textContent = displayPath || '~/';
    if (input) input.value = state.currentWorkspace;
    if (current) current.innerHTML = `<i class="fas fa-folder-open"></i> Current: ${state.currentWorkspace}`;
}

function showWorkspaceDialog(targetPath) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('workspaceDialog');
        const messageEl = document.getElementById('workspaceDialogMessage');
        const cancelBtn = document.getElementById('workspaceDialogCancel');
        const newChatBtn = document.getElementById('workspaceDialogNewChat');

        if (!dialog || !messageEl || !cancelBtn || !newChatBtn) {
            resolve(false);
            return;
        }

        const displayPath = targetPath.split('/').slice(-2).join('/') || targetPath;
        messageEl.innerHTML = `Switch to <span class="workspace-path-highlight">${escapeHtml(displayPath)}</span>? This will start a new chat.`;
        dialog.classList.add('show');

        const cleanup = () => {
            dialog.classList.remove('show');
            cancelBtn.onclick = null;
            newChatBtn.onclick = null;
            dialog.onclick = null;
        };

        cancelBtn.onclick = () => {
            cleanup();
            resolve(false);
        };

        newChatBtn.onclick = () => {
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

async function applyWorkspaceChange(workspace, slotNumber = null) {
    state.currentWorkspace = workspace;
    updateWorkspaceDisplay();

    try {
        await api.saveSettings({ workspace: state.currentWorkspace });
        if (slotNumber !== null) {
            activateSlot(slotNumber);
        } else {
            saveWorkspaceToSlot(state.currentWorkspace);
        }
        await createNewChat();
        showNotification('Workspace changed');
    } catch (error) {
        console.error('Error saving workspace:', error);
    }
}

async function selectCurrentDir() {
    const newWorkspace = state.browserCurrentPath;
    closeBrowser();

    if (newWorkspace === state.currentWorkspace) {
        return;
    }

    if (hasActiveConversation(state.chatHistory)) {
        const confirmed = await showWorkspaceDialog(newWorkspace);
        if (!confirmed) return;
    }

    await applyWorkspaceChange(newWorkspace);
}

async function switchWorkspace() {
    const { newActive, targetWorkspace } = getNextWorkspace();

    if (!targetWorkspace) {
        activateSlot(newActive);
        showNotification(`Select folder for workspace ${newActive}`, 'info');
        browseWorkspace();
        return;
    }

    if (hasActiveConversation(state.chatHistory)) {
        const confirmed = await showWorkspaceDialog(targetWorkspace);
        if (!confirmed) return;
    }

    await applyWorkspaceChange(targetWorkspace, newActive);
}

async function loadBrowserDirectory(path) {
    const listEl = DOM.get('browserList');
    const pathEl = DOM.get('browserPath');
    const searchEl = document.getElementById('browserSearch');

    if (!listEl) return;

    listEl.innerHTML = '<div class="loading">Loading...</div>';
    if (searchEl) searchEl.value = '';

    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (data.error) {
            listEl.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        state.browserCurrentPath = data.current || path;
        state.browserItems = data.items || [];
        if (pathEl) pathEl.textContent = state.browserCurrentPath;

        renderBrowserItems(state.browserItems);
    } catch (error) {
        listEl.innerHTML = `<div class="error">Failed to load directory</div>`;
        console.error('Error loading directory:', error);
    }
}

const browserState = {
    selectedIndex: -1,
    query: '',
    debounceTimer: null
};

const BROWSER_DEBOUNCE_MS = 300;

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    const escaped = escapeHtml(text);
    return escaped.replace(new RegExp(`(${escapeRegex(query)})`, 'gi'), '<mark>$1</mark>');
}

function renderBrowserItems(items, showPath = false) {
    const listEl = DOM.get('browserList');
    if (!listEl) return;

    browserState.selectedIndex = -1;

    if (items.length === 0) {
        listEl.innerHTML = '<div class="empty">No matching folders</div>';
        return;
    }

    listEl.innerHTML = items.map(item => {
        const highlightedName = highlightMatch(item.name, browserState.query);
        const pathHtml = showPath && item.display_path
            ? `<span class="browser-item-path">${escapeHtml(item.display_path)}</span>`
            : '';
        return `
            <div class="browser-item directory${showPath ? ' with-path' : ''}" data-path="${encodeURIComponent(item.path)}">
                <i class="fas fa-folder"></i>
                <span class="browser-item-name">${highlightedName}</span>${pathHtml}
            </div>
        `;
    }).join('');
}

function getBrowserElements() {
    return {
        search: document.getElementById('browserSearch'),
        clearBtn: document.getElementById('browserClearBtn'),
        list: DOM.get('browserList')
    };
}

function updateClearButton() {
    const { search, clearBtn } = getBrowserElements();
    if (search && clearBtn) {
        clearBtn.style.display = search.value ? 'block' : 'none';
    }
}

function clearBrowserSearch() {
    const { search } = getBrowserElements();
    if (search) {
        search.value = '';
        search.focus();
    }
    browserState.query = '';
    updateClearButton();
    renderBrowserItems(state.browserItems || []);
}

function filterBrowserList() {
    const { search, list } = getBrowserElements();
    if (!search) return;

    const query = search.value.trim();
    browserState.query = query;
    updateClearButton();

    if (browserState.debounceTimer) {
        clearTimeout(browserState.debounceTimer);
        browserState.debounceTimer = null;
    }

    if (!query) {
        renderBrowserItems(state.browserItems || []);
        return;
    }

    const queryLower = query.toLowerCase();
    if (query.length < 2) {
        const filtered = (state.browserItems || []).filter(item =>
            item.name.toLowerCase().includes(queryLower)
        );
        renderBrowserItems(filtered);
        return;
    }

    const displayPath = state.browserCurrentPath.replace(/^\/home\/[^/]+/, '~');
    browserState.debounceTimer = setTimeout(async () => {
        if (list) list.innerHTML = `<div class="loading">Searching in ${escapeHtml(displayPath)}...</div>`;

        try {
            const response = await fetch(`/api/search-folders?query=${encodeURIComponent(query)}&path=${encodeURIComponent(state.browserCurrentPath)}`);
            const data = await response.json();
            renderBrowserItems(data.items || [], true);
        } catch (error) {
            log.error('Error searching folders:', error);
            renderBrowserItems([]);
        }
    }, BROWSER_DEBOUNCE_MS);
}

function handleBrowserKeydown(e) {
    const { list } = getBrowserElements();
    if (!list) return;

    const items = list.querySelectorAll('.browser-item');
    if (items.length === 0) return;

    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            browserState.selectedIndex = Math.min(browserState.selectedIndex + 1, items.length - 1);
            updateBrowserSelection(items);
            break;
        case 'ArrowUp':
            e.preventDefault();
            browserState.selectedIndex = Math.max(browserState.selectedIndex - 1, 0);
            updateBrowserSelection(items);
            break;
        case 'Enter':
            if (browserState.selectedIndex >= 0) {
                e.preventDefault();
                const selectedItem = items[browserState.selectedIndex];
                if (selectedItem) {
                    loadBrowserDirectory(decodeURIComponent(selectedItem.dataset.path));
                    clearBrowserSearch();
                }
            }
            break;
        case 'Escape':
            clearBrowserSearch();
            break;
    }
}

function updateBrowserSelection(items) {
    items.forEach((item, index) => {
        item.classList.toggle('selected', index === browserState.selectedIndex);
    });
    const selected = items[browserState.selectedIndex];
    if (selected) {
        selected.scrollIntoView({ block: 'nearest' });
    }
}

function setupBrowserListEvents() {
    const listEl = DOM.get('browserList');
    if (!listEl) return;

    listEl.addEventListener('click', (e) => {
        const item = e.target.closest('.browser-item');
        if (!item) return;

        const path = decodeURIComponent(item.dataset.path);
        const type = item.dataset.type;

        if (type === 'directory') {
            loadBrowserDirectory(path);
        }
    });
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
window.navigateToParent = navigateToParent;
window.filterBrowserList = filterBrowserList;
window.clearBrowserSearch = clearBrowserSearch;
window.handleBrowserKeydown = handleBrowserKeydown;
window.selectCurrentDir = selectCurrentDir;
window.loadBrowserDirectory = loadBrowserDirectory;
window.renderBrowserItems = renderBrowserItems;
window.switchWorkspace = switchWorkspace;
window.updateModelFromHeader = updateModelFromHeader;
window.updateProviderFromHeader = updateProviderFromHeader;
window.handleKeyDown = handleKeyDown;
window.autoResize = autoResize;
window.sendMessage = sendMessage;

let draggedShortcutIndex = null;
let shortcutsContainerInitialized = false;

function getShortcutWrapper(element) {
    return element.closest('.custom-shortcut');
}

function initShortcutsContainer(container) {
    if (shortcutsContainerInitialized) return;
    shortcutsContainerInitialized = true;

    container.addEventListener('click', (e) => {
        const wrapper = getShortcutWrapper(e.target);
        if (!wrapper) return;

        if (e.target.closest('.shortcut-delete')) {
            e.stopPropagation();
            handleDeleteShortcut(wrapper.dataset.id);
        } else if (e.target.closest('.shortcut-edit')) {
            e.stopPropagation();
            toggleAddShortcutModal(wrapper.dataset.id);
        } else if (e.target.closest('.shortcut-label')) {
            const shortcuts = getShortcuts();
            const shortcut = shortcuts.find(s => s.id === wrapper.dataset.id);
            if (shortcut) window.sendSuggestion(shortcut.prompt);
        }
    });

    container.addEventListener('dragstart', (e) => {
        const wrapper = getShortcutWrapper(e.target);
        if (!wrapper) return;
        draggedShortcutIndex = parseInt(wrapper.dataset.index, 10);
        wrapper.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });

    container.addEventListener('dragend', (e) => {
        const wrapper = getShortcutWrapper(e.target);
        if (wrapper) wrapper.classList.remove('dragging');
        draggedShortcutIndex = null;
    });

    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        const wrapper = getShortcutWrapper(e.target);
        if (!wrapper) return;
        e.dataTransfer.dropEffect = 'move';
        const index = parseInt(wrapper.dataset.index, 10);
        if (draggedShortcutIndex !== null && draggedShortcutIndex !== index) {
            wrapper.classList.add('drag-over');
        }
    });

    container.addEventListener('dragleave', (e) => {
        const wrapper = getShortcutWrapper(e.target);
        if (wrapper) wrapper.classList.remove('drag-over');
    });

    container.addEventListener('drop', (e) => {
        e.preventDefault();
        const wrapper = getShortcutWrapper(e.target);
        if (!wrapper) return;
        wrapper.classList.remove('drag-over');
        const index = parseInt(wrapper.dataset.index, 10);
        if (draggedShortcutIndex !== null && draggedShortcutIndex !== index) {
            handleReorderShortcuts(draggedShortcutIndex, index);
        }
    });
}

function renderCustomShortcuts() {
    const container = document.querySelector('.input-quick-shortcuts');
    if (!container) return;

    initShortcutsContainer(container);
    container.querySelectorAll('.custom-shortcut').forEach(el => el.remove());

    const shortcuts = getShortcuts();

    shortcuts.forEach((shortcut, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'shortcut-btn custom-shortcut';
        wrapper.title = shortcut.prompt;
        wrapper.draggable = true;
        wrapper.dataset.id = shortcut.id;
        wrapper.dataset.index = index;

        wrapper.innerHTML = `
            <span class="shortcut-label">${shortcut.label}</span>
            <span class="shortcut-actions">
                <span class="shortcut-edit"><i class="fas fa-pen"></i></span>
                <span class="shortcut-delete">&times;</span>
            </span>
        `;
        container.appendChild(wrapper);
    });
}

function handleReorderShortcuts(fromIndex, toIndex) {
    reorderShortcuts(fromIndex, toIndex);
    renderCustomShortcuts();
}

function handleDeleteShortcut(id) {
    deleteShortcut(id);
    renderCustomShortcuts();
}

function handleSaveShortcut() {
    if (saveShortcut()) {
        renderCustomShortcuts();
        toggleAddShortcutModal();
    }
}

window.toggleAddShortcutModal = toggleAddShortcutModal;
window.saveShortcut = handleSaveShortcut;
window.renderCustomShortcuts = renderCustomShortcuts;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
    initDefaultShortcuts();
    migrateShortcutsWithIds(getShortcuts());
    renderCustomShortcuts();

    document.getElementById('addShortcutBtn')?.addEventListener('click', () => toggleAddShortcutModal());

    document.getElementById('addShortcutModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'addShortcutModal') {
            toggleAddShortcutModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (!isModalOpen()) return;
        if (e.key === 'Escape') {
            toggleAddShortcutModal();
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSaveShortcut();
        }
    });
});

