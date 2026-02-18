import { CONSTANTS } from './state.js';

const { CACHE_PREFIX, CACHE_META_KEY, MAX_CACHED_CHATS } = CONSTANTS;

export function saveChatToCache(chatId, messages, streamingContent = '') {
    if (!chatId) return;
    try {
        const cacheData = {
            messages,
            streamingContent,
            timestamp: Date.now(),
            synced: false
        };
        localStorage.setItem(CACHE_PREFIX + chatId, JSON.stringify(cacheData));
        console.log('[CACHE] Saved chat to cache:', chatId, 'messages:', messages.length);
        updateCacheMeta(chatId);
    } catch (e) {
        console.error('[CACHE] Failed to save to cache:', e);
    }
}

export function loadChatFromCache(chatId) {
    if (!chatId) return null;
    try {
        const cached = localStorage.getItem(CACHE_PREFIX + chatId);
        if (cached) {
            const data = JSON.parse(cached);
            console.log('[CACHE] Loaded chat from cache:', chatId, 'messages:', data.messages?.length);
            return data;
        }
    } catch (e) {
        console.error('[CACHE] Failed to load from cache:', e);
    }
    return null;
}

export function markCacheSynced(chatId) {
    if (!chatId) return;
    try {
        const cached = localStorage.getItem(CACHE_PREFIX + chatId);
        if (cached) {
            const data = JSON.parse(cached);
            data.synced = true;
            data.syncedAt = Date.now();
            localStorage.setItem(CACHE_PREFIX + chatId, JSON.stringify(data));
        }
    } catch (e) {
        console.error('[CACHE] Failed to mark synced:', e);
    }
}

function updateCacheMeta(chatId) {
    try {
        let meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        meta[chatId] = Date.now();

        const chatIds = Object.keys(meta).sort((a, b) => meta[b] - meta[a]);
        if (chatIds.length > MAX_CACHED_CHATS) {
            chatIds.slice(MAX_CACHED_CHATS).forEach(id => {
                delete meta[id];
                localStorage.removeItem(CACHE_PREFIX + id);
            });
        }

        localStorage.setItem(CACHE_META_KEY, JSON.stringify(meta));
    } catch (e) {
        console.error('[CACHE] Failed to update meta:', e);
    }
}

export function getUnsyncedChats() {
    const unsynced = [];
    try {
        const meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        Object.keys(meta).forEach(chatId => {
            const cached = localStorage.getItem(CACHE_PREFIX + chatId);
            if (cached) {
                const data = JSON.parse(cached);
                if (!data.synced && data.messages?.length > 0) {
                    unsynced.push({ chatId, ...data });
                }
            }
        });
    } catch (e) {
        console.error('[CACHE] Failed to get unsynced:', e);
    }
    return unsynced;
}

export function clearChatCache(chatId) {
    try {
        localStorage.removeItem(CACHE_PREFIX + chatId);
        let meta = JSON.parse(localStorage.getItem(CACHE_META_KEY) || '{}');
        delete meta[chatId];
        localStorage.setItem(CACHE_META_KEY, JSON.stringify(meta));
    } catch (e) {
        console.error('[CACHE] Failed to clear cache:', e);
    }
}

