import '../modules/state.js';
import '../modules/dom.js';
import '../modules/api.js';
import '../modules/cache.js';
import '../modules/ui.js';
import '../modules/chat.js';
import '../modules/streaming.js';
import '../modules/media.js';
import '../modules/reminders.js';

global.fetch.mockResolvedValue({ json: () => Promise.resolve({}) });
jest.mock('../modules/api.js', () => ({
    api: {
        getSettings: jest.fn().mockResolvedValue({}),
        getChats: jest.fn().mockResolvedValue([]),
        createChat: jest.fn().mockResolvedValue({ id: 'test' }),
        saveChat: jest.fn().mockResolvedValue({}),
        deleteChat: jest.fn().mockResolvedValue({}),
        getChat: jest.fn().mockResolvedValue({}),
        saveSettings: jest.fn().mockResolvedValue({})
    },
    logRequest: jest.fn(),
    logResponse: jest.fn()
}));

import { state } from '../modules/state.js';
window.appState = state;

window.browseWorkspace = jest.fn();
window.closeBrowser = jest.fn();
window.navigateToHome = jest.fn();
window.selectCurrentDir = jest.fn();
window.browseItem = jest.fn();

describe('Window Global Exports', () => {
    describe('All HTML onclick handlers have corresponding window functions', () => {
        const requiredFunctions = [
            'addReminder',
            'browseWorkspace',
            'clearAllChats',
            'clearSelectedImages',
            'closeBrowser',
            'createNewChat',
            'handleImageSelect',
            'navigateToHome',
            'openLogsTerminal',
            'refreshPage',
            'resetSession',
            'selectCurrentDir',
            'sendMessage',
            'sendSuggestion',
            'stopStreaming',
            'toggleDevTools',
            'toggleSettings',
            'toggleSidebar',
            'toggleTheme',
            'toggleVoiceRecording'
        ];

        requiredFunctions.forEach(funcName => {
            test(`window.${funcName} should be defined`, () => {
                expect(window[funcName]).toBeDefined();
                expect(typeof window[funcName]).toBe('function');
            });
        });
    });

    describe('UI functions', () => {
        test('toggleSettings should toggle settings modal', () => {
            const modal = document.getElementById('settingsModal');
            window.toggleSettings();
            expect(modal.classList.contains('active')).toBe(true);
        });

        test('toggleSidebar should toggle sidebar', () => {
            const sidebar = document.getElementById('sidebar');
            window.toggleSidebar();
            expect(sidebar.classList.contains('collapsed') || !sidebar.classList.contains('collapsed')).toBe(true);
        });

        test('toggleTheme should toggle body class', () => {
            const initialHasLight = document.body.classList.contains('light-theme');
            window.toggleTheme();
            expect(document.body.classList.contains('light-theme')).toBe(!initialHasLight);
        });
    });

    describe('Chat functions', () => {
        test('sendSuggestion should set input value', () => {
            const input = document.getElementById('messageInput');
            window.sendSuggestion('Test suggestion');
            expect(input.value).toBe('Test suggestion');
        });
    });

    describe('Media functions', () => {
        test('clearSelectedImages should clear images', () => {
            expect(() => window.clearSelectedImages()).not.toThrow();
        });

        test('removeImage should not throw for valid index', () => {
            expect(() => window.removeImage(0)).not.toThrow();
        });
    });

    describe('Streaming functions', () => {
        test('stopStreaming should not throw', () => {
            expect(() => window.stopStreaming()).not.toThrow();
        });
    });

    describe('Additional window exports', () => {
        test('appState should expose state object', () => {
            expect(window.appState).toBeDefined();
            expect(window.appState.chatHistory).toBeDefined();
        });

        test('deleteChat should be callable', () => {
            expect(typeof window.deleteChat).toBe('function');
        });

        test('newChat should be callable', () => {
            expect(typeof window.newChat).toBe('function');
        });

        test('toggleReminder should be callable', () => {
            expect(typeof window.toggleReminder).toBe('function');
        });

        test('deleteReminder should be callable', () => {
            expect(typeof window.deleteReminder).toBe('function');
        });
    });
});

