import { state } from '../modules/state.js';
import { DOM } from '../modules/dom.js';
import {
    WELCOME_HTML,
    generateMessageId,
    renderChatMessages,
    createMessageHTML,
    addMessage,
    newChat,
    loadChat,
    deleteChat,
    loadChatList,
    renderChatList,
    hideWelcome,
    createNewChat,
    clearAllChats
} from '../modules/chat.js';

describe('Chat Module', () => {
    beforeEach(() => {
        state.chatHistory = [];
        state.currentChatId = null;
        global.fetch.mockReset();
        DOM.clear();
    });

    describe('WELCOME_HTML', () => {
        test('should contain welcome message', () => {
            expect(WELCOME_HTML).toContain('welcome-message');
        });

        test('should contain quick action buttons', () => {
            expect(WELCOME_HTML).toContain('quick-actions');
            expect(WELCOME_HTML).toContain('action-btn');
        });
    });

    describe('generateMessageId', () => {
        test('should generate unique message ID', () => {
            const id1 = generateMessageId('chat1', 0, 'Hello');
            const id2 = generateMessageId('chat1', 1, 'World');

            expect(id1).not.toBe(id2);
        });

        test('should include chat id and index in generated ID', () => {
            const id = generateMessageId('chat1', 0, 'Hello');

            expect(id).toContain('chat1');
            expect(id).toContain('0');
        });
    });

    describe('createMessageHTML', () => {
        test('should create user message HTML with avatar', () => {
            const html = createMessageHTML('user', 'Hello there', 0, 'msg-1');

            expect(html).toContain('avatar');
            expect(html).toContain('fa-user');
            expect(html).toContain('Hello there');
        });

        test('should create assistant message HTML with avatar', () => {
            const html = createMessageHTML('assistant', 'Hi!', 0, 'msg-2');

            expect(html).toContain('avatar');
            expect(html).toContain('content');
        });
    });

    describe('addMessage', () => {
        test('should add message to chat history', () => {
            state.currentChatId = 'test-chat';
            addMessage('user', 'Test message', true);
            
            expect(state.chatHistory.length).toBe(1);
            expect(state.chatHistory[0].role).toBe('user');
            expect(state.chatHistory[0].content).toBe('Test message');
        });
    });

    describe('newChat', () => {
        test('should reset chat state', async () => {
            state.currentChatId = 'old-chat';
            state.chatHistory = [{ role: 'user', content: 'old message' }];
            
            await newChat();
            
            expect(state.currentChatId).toBeNull();
            expect(state.chatHistory).toEqual([]);
        });

        test('should show welcome message', async () => {
            await newChat();
            
            const container = document.getElementById('chatMessages');
            expect(container.innerHTML).toContain('welcome-message');
        });
    });

    describe('renderChatList', () => {
        test('should render empty state when no chats', () => {
            DOM.clear();
            renderChatList([]);

            const history = document.getElementById('chatHistory');
            expect(history.innerHTML).toContain('No conversations yet');
        });

        test('should render chat items', () => {
            const chats = [
                { id: '1', title: 'First Chat', updated_at: new Date().toISOString() },
                { id: '2', title: 'Second Chat', updated_at: new Date().toISOString() }
            ];
            
            renderChatList(chats);
            
            const history = document.getElementById('chatHistory');
            expect(history.querySelectorAll('.chat-history-item').length).toBe(2);
        });
    });

    describe('hideWelcome', () => {
        test('should remove welcome message', () => {
            const container = document.getElementById('chatMessages');
            container.innerHTML = '<div class="welcome-message">Welcome!</div>';
            
            hideWelcome();
            
            expect(container.querySelector('.welcome-message')).toBeNull();
        });
    });

    describe('window global assignments', () => {
        test('sendSuggestion should be on window', () => {
            expect(window.sendSuggestion).toBeDefined();
        });

        test('deleteChat should be on window', () => {
            expect(window.deleteChat).toBeDefined();
        });

        test('newChat should be on window', () => {
            expect(window.newChat).toBeDefined();
        });

        test('createNewChat should be on window', () => {
            expect(window.createNewChat).toBeDefined();
        });

        test('clearAllChats should be on window', () => {
            expect(window.clearAllChats).toBeDefined();
        });
    });
});

