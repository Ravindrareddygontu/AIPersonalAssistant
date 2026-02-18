import { CONSTANTS, state, activeRequests, pendingStreamPolls } from '../modules/state.js';

describe('State Module', () => {
    describe('CONSTANTS', () => {
        test('MAX_CONCURRENT_REQUESTS should be 2', () => {
            expect(CONSTANTS.MAX_CONCURRENT_REQUESTS).toBe(2);
        });

        test('CACHE_PREFIX should be defined', () => {
            expect(CONSTANTS.CACHE_PREFIX).toBe('chat_cache_');
        });

        test('MAX_CACHED_CHATS should be 50', () => {
            expect(CONSTANTS.MAX_CACHED_CHATS).toBe(50);
        });

        test('all constants should be defined', () => {
            expect(CONSTANTS.CACHE_META_KEY).toBeDefined();
            expect(CONSTANTS.CACHE_AUTO_SAVE_INTERVAL).toBeDefined();
            expect(CONSTANTS.MAX_POLL_DURATION).toBeDefined();
            expect(CONSTANTS.STREAMING_UPDATE_INTERVAL).toBeDefined();
        });
    });

    describe('state object', () => {
        test('should have initial chatHistory as empty array', () => {
            expect(state.chatHistory).toEqual([]);
        });

        test('should have currentChatId as null initially', () => {
            expect(state.currentChatId).toBeNull();
        });

        test('should have isProcessing as false initially', () => {
            expect(state.isProcessing).toBe(false);
        });

        test('should have default workspace', () => {
            expect(state.currentWorkspace).toBe('~');
        });

        test('should have default model', () => {
            expect(state.currentModel).toBe('claude-opus-4.5');
        });

        test('should have selectedImages as empty array', () => {
            expect(state.selectedImages).toEqual([]);
        });

        test('should have isRecording as false', () => {
            expect(state.isRecording).toBe(false);
        });
    });

    describe('activeRequests Map', () => {
        test('should be a Map instance', () => {
            expect(activeRequests).toBeInstanceOf(Map);
        });

        test('should be empty initially', () => {
            expect(activeRequests.size).toBe(0);
        });
    });

    describe('pendingStreamPolls Map', () => {
        test('should be a Map instance', () => {
            expect(pendingStreamPolls).toBeInstanceOf(Map);
        });
    });
});

