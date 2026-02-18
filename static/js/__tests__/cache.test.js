import { saveChatToCache, loadChatFromCache, markCacheSynced, getUnsyncedChats, clearChatCache } from '../modules/cache.js';

describe('Cache Module', () => {
    const testChatId = 'test-chat-123';
    const testMessages = [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi there!' }
    ];

    describe('saveChatToCache', () => {
        test('should save chat data to localStorage', () => {
            saveChatToCache(testChatId, testMessages);

            expect(localStorage.setItem).toHaveBeenCalled();
        });

        test('should not save if chatId is null', () => {
            const callCountBefore = localStorage.setItem.mock.calls.length;
            saveChatToCache(null, testMessages);
            expect(localStorage.setItem.mock.calls.length).toBe(callCountBefore);
        });

        test('should include streaming content if provided', () => {
            saveChatToCache(testChatId, testMessages, 'streaming...');

            const calls = localStorage.setItem.mock.calls;
            const chatCacheCall = calls.find(c => c[0].includes('chat_cache_'));
            expect(chatCacheCall).toBeDefined();
            const savedData = JSON.parse(chatCacheCall[1]);
            expect(savedData.streamingContent).toBe('streaming...');
        });
    });

    describe('loadChatFromCache', () => {
        test('should load chat data from localStorage', () => {
            const cacheData = { messages: testMessages, synced: false, timestamp: Date.now() };
            localStorage.getItem.mockReturnValueOnce(JSON.stringify(cacheData));

            const result = loadChatFromCache(testChatId);
            expect(result.messages).toEqual(testMessages);
        });

        test('should return null for non-existent chat', () => {
            localStorage.getItem.mockReturnValueOnce(null);
            const result = loadChatFromCache('non-existent');
            expect(result).toBeNull();
        });

        test('should return null if chatId is null', () => {
            const result = loadChatFromCache(null);
            expect(result).toBeNull();
        });
    });

    describe('markCacheSynced', () => {
        test('should mark chat as synced', () => {
            const cacheData = { messages: testMessages, synced: false };
            localStorage.getItem.mockReturnValueOnce(JSON.stringify(cacheData));

            markCacheSynced(testChatId);

            const calls = localStorage.setItem.mock.calls;
            const lastCall = calls[calls.length - 1];
            const updatedData = JSON.parse(lastCall[1]);
            expect(updatedData.synced).toBe(true);
            expect(updatedData.syncedAt).toBeDefined();
        });
    });

    describe('getUnsyncedChats', () => {
        test('should return array of unsynced chats', () => {
            const meta = { 'chat1': Date.now(), 'chat2': Date.now() };
            const unsyncedChat = { messages: [{ role: 'user', content: 'test' }], synced: false };
            const syncedChat = { messages: [{ role: 'user', content: 'test' }], synced: true };

            localStorage.getItem.mockImplementation((key) => {
                if (key === 'chat_cache_meta') return JSON.stringify(meta);
                if (key === 'chat_cache_chat1') return JSON.stringify(unsyncedChat);
                if (key === 'chat_cache_chat2') return JSON.stringify(syncedChat);
                return null;
            });

            const result = getUnsyncedChats();
            expect(result.length).toBe(1);
            expect(result[0].chatId).toBe('chat1');
        });
    });

    describe('clearChatCache', () => {
        test('should remove chat from cache and meta', () => {
            const meta = { [testChatId]: Date.now() };
            localStorage.getItem.mockImplementation((key) => {
                if (key === 'chat_cache_meta') return JSON.stringify(meta);
                if (key === `chat_cache_${testChatId}`) return JSON.stringify({ messages: [] });
                return null;
            });

            clearChatCache(testChatId);

            expect(localStorage.removeItem).toHaveBeenCalledWith(`chat_cache_${testChatId}`);
        });
    });
});

