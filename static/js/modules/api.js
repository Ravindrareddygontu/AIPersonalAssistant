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

export const api = {
    async getChats() {
        const url = '/api/chats';
        logRequest('GET', url);
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, { chats_count: data.length });
        return data;
    },

    async getChat(chatId) {
        const url = `/api/chats/${chatId}?_t=${Date.now()}`;
        logRequest('GET', url);
        const response = await fetch(url, { cache: 'no-store' });
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        return data;
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
        const data = await response.json();
        logResponse('POST', url, response.status, data);
        return data;
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
        const data = await response.json();
        logResponse('PUT', url, response.status, data);
        return data;
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
        const data = await response.json();
        logResponse('PUT', url, response.status, data);
        return data;
    },

    async deleteChat(chatId) {
        const url = `/api/chats/${chatId}`;
        logRequest('DELETE', url);
        const response = await fetch(url, { method: 'DELETE' });
        const data = await response.json();
        logResponse('DELETE', url, response.status, data);
        return data;
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
    }
};

