import { DOM } from './dom.js';
import { state } from './state.js';

export function showNotification(message, type = 'info') {
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
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
    }, 3000);
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
    const statusBar = DOM.get('inputStatusBar');
    if (!statusBar) return;

    statusBar.style.display = 'flex';

    const statusText = statusBar.querySelector('.status-text');
    if (statusText) {
        statusText.textContent = statusMessage;
    }

    const statusIcon = statusBar.querySelector('.status-icon');
    if (statusIcon) {
        const iconClass = getStatusIcon(statusMessage);
        statusIcon.className = `fas ${iconClass} fa-spin status-icon`;
    }
}

export function updateTypingIndicatorText(text) {
    const statusBar = DOM.get('inputStatusBar');
    if (statusBar) {
        const statusText = statusBar.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = text;
        }

        const statusIcon = statusBar.querySelector('.status-icon');
        if (statusIcon) {
            const iconClass = getStatusIcon(text);
            statusIcon.className = `fas ${iconClass} fa-spin status-icon`;
        }
    }
}

export function hideTypingIndicator() {
    const statusBar = DOM.get('inputStatusBar');
    if (statusBar) {
        statusBar.style.display = 'none';
    }
}

export function updateTypingStatus(message) {
    updateTypingIndicatorText(message);
}

export function toggleSettings() {
    const modal = DOM.get('settingsModal');
    if (modal) {
        modal.classList.toggle('active');
    }
}

export function toggleBrowser() {
    const modal = DOM.get('browserModal');
    if (modal) {
        modal.classList.toggle('active');
    }
}

export function toggleDevTools() {
    const modal = DOM.get('devToolsModal');
    if (modal) {
        modal.classList.toggle('active');
    }
}

export function toggleSidebar() {
    const sidebar = DOM.get('sidebar');
    state.sidebarOpen = !state.sidebarOpen;
    sidebar.classList.toggle('collapsed', !state.sidebarOpen);
    localStorage.setItem('sidebarOpen', state.sidebarOpen);

    if (state.sidebarOpen) {
        sidebar.style.width = '280px';
    }
}

export function toggleTheme() {
    const body = document.body;
    const isDark = body.classList.toggle('light-theme');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');

    const themeIcon = document.querySelector('#themeToggle i');
    if (themeIcon) {
        themeIcon.classList.toggle('fa-moon', !isDark);
        themeIcon.classList.toggle('fa-sun', isDark);
    }
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

window.toggleSettings = toggleSettings;
window.toggleSidebar = toggleSidebar;
window.toggleDevTools = toggleDevTools;
window.toggleTheme = toggleTheme;
window.refreshPage = refreshPage;
window.openLogsTerminal = openLogsTerminal;
window.resetSession = resetSession;

