import { DOM } from '../modules/dom.js';
import {
    showNotification,
    showTypingIndicator,
    hideTypingIndicator,
    toggleSettings,
    toggleSidebar,
    toggleDevTools,
    toggleTheme,
    refreshPage,
    openLogsTerminal,
    resetSession
} from '../modules/ui.js';

describe('UI Module', () => {
    beforeEach(() => {
        DOM.clear();
    });

    describe('showNotification', () => {
        test('should create notification element', () => {
            showNotification('Test message');
            
            const notification = document.querySelector('.notification');
            expect(notification).not.toBeNull();
            expect(notification.textContent).toContain('Test message');
        });

        test('should remove existing notification before showing new one', () => {
            showNotification('First');
            showNotification('Second');
            
            const notifications = document.querySelectorAll('.notification');
            expect(notifications.length).toBe(1);
            expect(notifications[0].textContent).toContain('Second');
        });

        test('should add appropriate class for notification type', () => {
            showNotification('Error!', 'error');
            
            const notification = document.querySelector('.notification');
            expect(notification.classList.contains('notification-error')).toBe(true);
        });
    });

    describe('showTypingIndicator', () => {
        test('should show typing indicator with message when streaming message exists', () => {
            const streamingMsg = document.createElement('div');
            streamingMsg.className = 'message streaming';
            streamingMsg.innerHTML = `
                <div class="streaming-status" style="display: none;">
                    <i class="fas fa-circle-notch fa-spin streaming-status-icon"></i>
                    <span class="streaming-status-text"></span>
                </div>
            `;
            document.body.appendChild(streamingMsg);

            showTypingIndicator('Processing...');

            const status = streamingMsg.querySelector('.streaming-status');
            expect(status.style.display).toBe('flex');
            expect(status.querySelector('.streaming-status-text').textContent).toBe('Processing...');

            streamingMsg.remove();
        });
    });

    describe('hideTypingIndicator', () => {
        test('should hide typing indicator when streaming message exists', () => {
            const streamingMsg = document.createElement('div');
            streamingMsg.className = 'message streaming';
            streamingMsg.innerHTML = `
                <div class="streaming-status" style="display: flex;">
                    <i class="fas fa-circle-notch fa-spin streaming-status-icon"></i>
                    <span class="streaming-status-text">Processing...</span>
                </div>
            `;
            document.body.appendChild(streamingMsg);

            hideTypingIndicator();

            const status = streamingMsg.querySelector('.streaming-status');
            expect(status.style.display).toBe('none');

            streamingMsg.remove();
        });
    });

    describe('toggleSettings', () => {
        test('should toggle settings modal active class', () => {
            const modal = document.getElementById('settingsModal');
            
            toggleSettings();
            expect(modal.classList.contains('active')).toBe(true);
            
            toggleSettings();
            expect(modal.classList.contains('active')).toBe(false);
        });
    });

    describe('toggleSidebar', () => {
        test('should toggle sidebar collapsed class', () => {
            const sidebar = document.getElementById('sidebar');
            
            toggleSidebar();
            expect(sidebar.classList.contains('collapsed')).toBe(true);
            
            toggleSidebar();
            expect(sidebar.classList.contains('collapsed')).toBe(false);
        });

        test('should save state to localStorage', () => {
            toggleSidebar();
            expect(localStorage.setItem).toHaveBeenCalledWith('sidebarOpen', expect.any(Boolean));
        });
    });

    describe('toggleDevTools', () => {
        test('should toggle devTools modal active class', () => {
            const modal = document.getElementById('devToolsModal');
            
            toggleDevTools();
            expect(modal.classList.contains('active')).toBe(true);
        });
    });

    describe('toggleTheme', () => {
        test('should toggle light-theme class on body', () => {
            toggleTheme();
            expect(document.body.classList.contains('light-theme')).toBe(true);
            
            toggleTheme();
            expect(document.body.classList.contains('light-theme')).toBe(false);
        });

        test('should save theme preference to localStorage', () => {
            toggleTheme();
            expect(localStorage.setItem).toHaveBeenCalledWith('theme', expect.any(String));
        });
    });

    describe('refreshPage', () => {
        test('should be a function', () => {
            expect(typeof refreshPage).toBe('function');
        });
    });

    describe('window global assignments', () => {
        test('toggleSettings should be on window', () => {
            expect(window.toggleSettings).toBeDefined();
        });

        test('toggleSidebar should be on window', () => {
            expect(window.toggleSidebar).toBeDefined();
        });

        test('toggleTheme should be on window', () => {
            expect(window.toggleTheme).toBeDefined();
        });

        test('refreshPage should be on window', () => {
            expect(window.refreshPage).toBeDefined();
        });
    });
});

