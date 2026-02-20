import { DOM } from './dom.js';
import { state } from './state.js';

export function showNotification(message, type = 'info') {
    console.log('[UI] showNotification:', type, message);
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();

    const icons = {
        info: 'fa-info-circle',
        warning: 'fa-exclamation-triangle',
        error: 'fa-times-circle',
        success: 'fa-check-circle'
    };

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas ${icons[type] || icons.info} notification-icon"></i>
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="notification-close">
            <i class="fas fa-times"></i>
        </button>
    `;
    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentElement) {
            notification.classList.add('fade-out');
            setTimeout(() => notification.remove(), 300);
        }
    }, 4000);
}

function getStatusIcon(message) {
    const msg = message.toLowerCase();
    if (msg.includes('connecting') || msg.includes('reconnecting')) return 'fa-plug';
    if (msg.includes('sending')) return 'fa-paper-plane';
    if (msg.includes('processing') || msg.includes('thinking')) return 'fa-brain';
    if (msg.includes('streaming') || msg.includes('receiving')) return 'fa-stream';
    if (msg.includes('waiting')) return 'fa-hourglass-half';
    return 'fa-circle-notch';
}

export function showTypingIndicator(statusMessage = 'Thinking...') {
    const streamingStatus = document.querySelector('.message.streaming .streaming-status');
    if (streamingStatus) {
        streamingStatus.style.display = 'flex';
        const statusText = streamingStatus.querySelector('.streaming-status-text');
        const statusIcon = streamingStatus.querySelector('.streaming-status-icon');
        if (statusText) statusText.textContent = statusMessage;
        if (statusIcon) {
            const iconClass = getStatusIcon(statusMessage);
            statusIcon.className = `fas ${iconClass} fa-spin streaming-status-icon`;
        }
    }
}

export function updateTypingIndicatorText(text) {
    const streamingStatus = document.querySelector('.message.streaming .streaming-status');
    if (streamingStatus) {
        const statusText = streamingStatus.querySelector('.streaming-status-text');
        const statusIcon = streamingStatus.querySelector('.streaming-status-icon');

        if (statusText) {
            statusText.classList.remove('fade-in');
            void statusText.offsetWidth;

            statusText.textContent = text;
            statusText.classList.add('shimmer', 'fade-in');

            setTimeout(() => statusText.classList.remove('fade-in'), 250);
        }

        if (statusIcon) {
            const iconClass = getStatusIcon(text);
            statusIcon.className = `fas ${iconClass} fa-spin streaming-status-icon`;
        }
    }
}

export function hideTypingIndicator() {
    const streamingStatus = document.querySelector('.message.streaming .streaming-status');
    if (streamingStatus) {
        streamingStatus.style.display = 'none';
        const statusText = streamingStatus.querySelector('.streaming-status-text');
        if (statusText) {
            statusText.classList.remove('shimmer', 'fade-in');
        }
    }
}

export function updateTypingStatus(message) {
    updateTypingIndicatorText(message);
}

export function closeModalWithAnimation(modal, activeClass = 'active') {
    if (!modal) return Promise.resolve();
    return new Promise((resolve) => {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove(activeClass, 'closing');
            resolve();
        }, 500);
    });
}

export function toggleModal(modal) {
    if (!modal) return;
    if (modal.classList.contains('active')) {
        closeModalWithAnimation(modal);
    } else {
        modal.classList.add('active');
    }
}

export function toggleSettings() {
    const modal = DOM.get('settingsModal');
    toggleModal(modal);
}

export function toggleBrowser() {
    const modal = DOM.get('browserModal');
    toggleModal(modal);
}

export function toggleDevTools() {
    const modal = DOM.get('devToolsModal');
    toggleModal(modal);
}

export function toggleSidebar() {
    const sidebar = DOM.get('sidebar');
    state.sidebarOpen = !state.sidebarOpen;
    sidebar.classList.toggle('collapsed', !state.sidebarOpen);
    localStorage.setItem('sidebarOpen', state.sidebarOpen);
}

export function toggleTheme() {
    const body = document.body;

    body.classList.add('theme-transitioning');

    const isDark = body.classList.toggle('light-theme');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');

    const themeIcon = document.querySelector('#themeToggle i');
    if (themeIcon) {
        themeIcon.classList.toggle('fa-moon', !isDark);
        themeIcon.classList.toggle('fa-sun', isDark);
    }

    setTimeout(() => {
        body.classList.remove('theme-transitioning');
    }, 500);
}

export function refreshPage() {
    window.location.reload();
}

export async function openLogsTerminal() {
    if (window.electronAPI?.openLogsTerminal) {
        await window.electronAPI.openLogsTerminal();
    } else {
        showNotification('Logs terminal only available in desktop app', 'info');
    }
}

export async function resetSession() {
    try {
        const response = await fetch('/api/chat/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace: state.currentWorkspace })
        });
        if (response.ok) {
            showNotification('Session reset successfully');
        } else {
            const data = await response.json();
            showNotification(data.message || 'Failed to reset session', 'error');
        }
    } catch (e) {
        showNotification('Error resetting session: ' + e.message, 'error');
    }
}

export function showConfirmDialog(message) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('confirmDialog');
        const messageEl = document.getElementById('confirmMessage');
        const cancelBtn = document.getElementById('confirmCancel');
        const deleteBtn = document.getElementById('confirmDelete');

        messageEl.textContent = message;
        dialog.classList.add('show');

        const cleanup = async (result) => {
            await closeModalWithAnimation(dialog, 'show');
            cancelBtn.onclick = null;
            deleteBtn.onclick = null;
            dialog.onclick = null;
            resolve(result);
        };

        cancelBtn.onclick = () => cleanup(false);
        deleteBtn.onclick = () => cleanup(true);
        dialog.onclick = (e) => {
            if (e.target === dialog) cleanup(false);
        };
    });
}

window.toggleSettings = toggleSettings;
window.toggleSidebar = toggleSidebar;
window.toggleDevTools = toggleDevTools;
window.toggleTheme = toggleTheme;
window.refreshPage = refreshPage;
window.openLogsTerminal = openLogsTerminal;
window.resetSession = resetSession;

