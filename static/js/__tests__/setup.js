global.fetch = jest.fn();

const localStorageStore = {};
const localStorageMock = {
    getItem: jest.fn((key) => localStorageStore[key] || null),
    setItem: jest.fn((key, value) => { localStorageStore[key] = String(value); }),
    removeItem: jest.fn((key) => { delete localStorageStore[key]; }),
    clear: jest.fn(() => { Object.keys(localStorageStore).forEach(key => delete localStorageStore[key]); }),
    get store() { return localStorageStore; }
};
Object.defineProperty(global, 'localStorage', { value: localStorageMock, writable: true });

global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = jest.fn();

beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    
    document.body.innerHTML = `
        <div id="chatMessages"></div>
        <div id="sidebar" class="sidebar"></div>
        <div id="settingsModal"></div>
        <div id="browserModal"></div>
        <div id="devToolsModal"></div>
        <input id="messageInput" />
        <button id="sendBtn"></button>
        <div id="typingIndicator"></div>
        <div id="imagePreviewArea" style="display: none;"></div>
        <div id="imagePreviewContainer"></div>
        <button id="imageBtn"></button>
        <button id="voiceBtn"><i id="voiceIcon" class="fas fa-microphone"></i></button>
        <input id="workspacePath" />
        <div id="browserPath"></div>
        <div id="browserList"></div>
        <div id="chatHistory"></div>
    `;
});

afterEach(() => {
    document.body.innerHTML = '';
});

