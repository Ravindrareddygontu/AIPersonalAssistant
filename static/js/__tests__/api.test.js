import { api, logRequest, logResponse } from '../modules/api.js';

describe('API Module', () => {
    beforeEach(() => {
        global.fetch.mockReset();
    });

    describe('logRequest', () => {
        test('should log request without throwing', () => {
            const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
            expect(() => logRequest('GET', '/api/test')).not.toThrow();
            consoleSpy.mockRestore();
        });
    });

    describe('logResponse', () => {
        test('should log response without throwing', () => {
            const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
            expect(() => logResponse('GET', '/api/test', 200, { data: 'test' })).not.toThrow();
            consoleSpy.mockRestore();
        });
    });

    describe('api.getSettings', () => {
        test('should fetch settings from /api/settings', async () => {
            const mockSettings = { workspace: '~', model: 'claude-opus-4.5' };
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve(mockSettings)
            });

            const result = await api.getSettings();
            
            expect(fetch).toHaveBeenCalledWith('/api/settings');
            expect(result).toEqual(mockSettings);
        });
    });

    describe('api.saveSettings', () => {
        test('should POST settings to /api/settings', async () => {
            const settings = { workspace: '/home/user' };
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'success' })
            });

            await api.saveSettings(settings);
            
            expect(fetch).toHaveBeenCalledWith('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
        });
    });

    describe('api.getChats', () => {
        test('should fetch chats from /api/chats', async () => {
            const mockChats = [{ id: '1', title: 'Chat 1' }];
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve(mockChats)
            });

            const result = await api.getChats();
            
            expect(fetch).toHaveBeenCalledWith('/api/chats');
            expect(result).toEqual(mockChats);
        });
    });

    describe('api.createChat', () => {
        test('should POST to /api/chats with workspace', async () => {
            const mockChat = { id: 'new-123', title: 'New Chat' };
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve(mockChat)
            });

            const result = await api.createChat('/home/user');
            
            expect(fetch).toHaveBeenCalledWith('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace: '/home/user' })
            });
            expect(result).toEqual(mockChat);
        });
    });

    describe('api.saveChat', () => {
        test('should PUT messages to /api/chats/:id', async () => {
            const messages = [{ role: 'user', content: 'Hello' }];
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'success' })
            });

            await api.saveChat('chat-123', messages);
            
            expect(fetch).toHaveBeenCalledWith('/api/chats/chat-123', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages })
            });
        });
    });

    describe('api.deleteChat', () => {
        test('should DELETE /api/chats/:id', async () => {
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'deleted' })
            });

            await api.deleteChat('chat-123');
            
            expect(fetch).toHaveBeenCalledWith('/api/chats/chat-123', {
                method: 'DELETE'
            });
        });
    });

    describe('api.getChat', () => {
        test('should GET /api/chats/:id with cache busting', async () => {
            const mockChat = { id: 'chat-123', messages: [] };
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve(mockChat)
            });

            const result = await api.getChat('chat-123');

            expect(fetch).toHaveBeenCalledWith(
                expect.stringContaining('/api/chats/chat-123'),
                expect.objectContaining({ cache: 'no-store' })
            );
            expect(result).toEqual(mockChat);
        });
    });

    describe('api.updateChatProvider', () => {
        test('should PUT provider to /api/chats/:id', async () => {
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'success' })
            });

            await api.updateChatProvider('chat-123', 'codex');

            expect(fetch).toHaveBeenCalledWith('/api/chats/chat-123', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: 'codex' })
            });
        });

        test('should update provider to auggie', async () => {
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'success' })
            });

            await api.updateChatProvider('chat-456', 'auggie');

            expect(fetch).toHaveBeenCalledWith('/api/chats/chat-456', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: 'auggie' })
            });
        });

        test('should return response data', async () => {
            const mockResponse = { status: 'success', provider: 'codex' };
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve(mockResponse)
            });

            const result = await api.updateChatProvider('chat-123', 'codex');
            expect(result).toEqual(mockResponse);
        });
    });

    describe('api.resetSession', () => {
        test('should POST to /api/chat/reset with workspace', async () => {
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'reset' })
            });

            await api.resetSession('/home/user/project');

            expect(fetch).toHaveBeenCalledWith('/api/chat/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ workspace: '/home/user/project' })
            });
        });

        test('should POST empty body when no workspace', async () => {
            global.fetch.mockResolvedValueOnce({
                json: () => Promise.resolve({ status: 'reset' })
            });

            await api.resetSession();

            expect(fetch).toHaveBeenCalledWith('/api/chat/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
        });
    });
});

