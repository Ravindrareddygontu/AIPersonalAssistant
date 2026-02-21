export function logRequest(method, url, body = null) {
    const fullUrl = new URL(url, window.location.origin).href;
    const bodyStr = body ? JSON.stringify(body).substring(0, 500) : 'None';
    console.log(`[REQUEST] ${method} ${fullUrl} | Body: ${bodyStr}`);
}

export function logResponse(method, url, status, body = null) {
    const fullUrl = new URL(url, window.location.origin).href;
    const bodyStr = body ? JSON.stringify(body).substring(0, 500) : 'None';
    console.log(`[RESPONSE] ${method} ${fullUrl} | Status: ${status} | Body: ${bodyStr}`);
}

async function handleResponse(response, method, url) {
    let data;
    try {
        data = await response.json();
    } catch (e) {
        console.error(`[API] Failed to parse JSON from ${method} ${url}:`, e);
        throw new Error(`Invalid JSON response from ${method} ${url}`);
    }

    logResponse(method, url, response.status, data);

    if (!response.ok) {
        const errorMsg = data?.error || data?.message || `HTTP ${response.status}`;
        console.error(`[API] ${method} ${url} failed:`, errorMsg);
        return { error: errorMsg, status: response.status };
    }

    return data;
}

export const api = {
    async getChats() {
        const url = '/api/chats';
        logRequest('GET', url);
        const response = await fetch(url);
        const data = await handleResponse(response, 'GET', url);
        if (!data.error) {
            logResponse('GET', url, response.status, { chats_count: data.length });
        }
        return data.error ? [] : data;
    },

    async getChat(chatId) {
        const url = `/api/chats/${chatId}?_t=${Date.now()}`;
        logRequest('GET', url);
        const response = await fetch(url, { cache: 'no-store' });
        return handleResponse(response, 'GET', url);
    },

    async createChat(workspace) {
        const url = '/api/chats';
        const body = { workspace };
        logRequest('POST', url, body);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return handleResponse(response, 'POST', url);
    },

    async saveChat(chatId, messages) {
        const url = `/api/chats/${chatId}`;
        const body = { messages };
        logRequest('PUT', url, body);
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return handleResponse(response, 'PUT', url);
    },

    async updateChatProvider(chatId, provider) {
        const url = `/api/chats/${chatId}`;
        const body = { provider };
        logRequest('PUT', url, body);
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return handleResponse(response, 'PUT', url);
    },

    async deleteChat(chatId) {
        const url = `/api/chats/${chatId}`;
        logRequest('DELETE', url);
        const response = await fetch(url, { method: 'DELETE' });
        return handleResponse(response, 'DELETE', url);
    },

    async getSettings() {
        const url = '/api/settings';
        logRequest('GET', url);
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        return data;
    },

    async saveSettings(settings) {
        const url = '/api/settings';
        logRequest('POST', url, settings);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        logResponse('POST', url, response.status, data);
        return data;
    },

    async resetSession(workspace) {
        const url = '/api/chat/reset';
        const body = workspace ? { workspace } : {};
        logRequest('POST', url, body);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        logResponse('POST', url, response.status, data);
        return data;
    },

    async getBotStatus() {
        const url = '/api/bots/status';
        logRequest('GET', url);
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        return data;
    },

    async controlBot(bot, action) {
        const url = '/api/bots/control';
        const body = { bot, action };
        logRequest('POST', url, body);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        logResponse('POST', url, response.status, data);
        return data;
    }
};

