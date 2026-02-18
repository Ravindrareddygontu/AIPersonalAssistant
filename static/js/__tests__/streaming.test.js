import { state, activeRequests } from '../modules/state.js';
import { DOM } from '../modules/dom.js';
import {
    getActiveRequestCount,
    hasActiveRequest,
    sendMessage,
    stopCurrentRequest
} from '../modules/streaming.js';

describe('Streaming Module', () => {
    beforeEach(() => {
        state.chatHistory = [];
        state.currentChatId = null;
        state.isProcessing = false;
        state.currentAbortController = null;
        activeRequests.clear();
        global.fetch.mockReset();
        DOM.clear();
    });

    describe('getActiveRequestCount', () => {
        test('should return 0 when no active requests', () => {
            expect(getActiveRequestCount()).toBe(0);
        });

        test('should return correct count', () => {
            activeRequests.set('chat1', {});
            activeRequests.set('chat2', {});
            
            expect(getActiveRequestCount()).toBe(2);
            
            activeRequests.clear();
        });
    });

    describe('hasActiveRequest', () => {
        test('should return false for non-existent chat', () => {
            expect(hasActiveRequest('non-existent')).toBe(false);
        });

        test('should return true for active chat', () => {
            activeRequests.set('active-chat', {});
            
            expect(hasActiveRequest('active-chat')).toBe(true);
            
            activeRequests.clear();
        });
    });

    describe('stopCurrentRequest', () => {
        test('should abort current request', () => {
            const mockAbort = jest.fn();
            state.currentAbortController = { abort: mockAbort };
            
            stopCurrentRequest();
            
            expect(mockAbort).toHaveBeenCalled();
            expect(state.currentAbortController).toBeNull();
        });

        test('should reset processing state', () => {
            state.isProcessing = true;
            state.currentAbortController = { abort: jest.fn() };
            
            stopCurrentRequest();
            
            expect(state.isProcessing).toBe(false);
        });

        test('should re-enable send button', () => {
            const sendBtn = document.getElementById('sendBtn');
            sendBtn.disabled = true;
            state.currentAbortController = { abort: jest.fn() };
            
            stopCurrentRequest();
            
            expect(sendBtn.disabled).toBe(false);
        });
    });

    describe('sendMessage', () => {
        test('should not send if message is empty', async () => {
            const input = document.getElementById('messageInput');
            input.value = '';
            
            await sendMessage();
            
            expect(fetch).not.toHaveBeenCalled();
        });

        test('should not send if already processing', async () => {
            const input = document.getElementById('messageInput');
            input.value = 'Test message';
            state.isProcessing = true;
            
            await sendMessage();
            
            expect(fetch).not.toHaveBeenCalled();
        });

        test('should create chat if none exists', async () => {
            const input = document.getElementById('messageInput');
            input.value = 'Test message';
            state.currentChatId = null;
            
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ id: 'new-chat-id' })
            });
            global.fetch.mockResolvedValueOnce({
                body: {
                    getReader: () => ({
                        read: jest.fn().mockResolvedValue({ done: true })
                    })
                }
            });
            
            await sendMessage();
            
            expect(fetch).toHaveBeenCalledWith('/api/chats', expect.any(Object));
        });
    });

    describe('window global assignments', () => {
        test('sendMessage should be on window', () => {
            expect(window.sendMessage).toBeDefined();
        });

        test('stopStreaming should be on window', () => {
            expect(window.stopStreaming).toBeDefined();
        });
    });
});

