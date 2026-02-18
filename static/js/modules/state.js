export const CONSTANTS = {
    MAX_CONCURRENT_REQUESTS: 2,
    CACHE_PREFIX: 'chat_cache_',
    CACHE_META_KEY: 'chat_cache_meta',
    MAX_CACHED_CHATS: 50,
    CACHE_AUTO_SAVE_INTERVAL: 3000,
    MAX_POLL_DURATION: 120,
    STREAMING_UPDATE_INTERVAL: 50
};

export const state = {
    chatHistory: [],
    currentChatId: null,
    isProcessing: false,
    currentRequestId: 0,
    currentWorkspace: '~',
    currentModel: 'claude-opus-4.5',
    availableModels: [],
    historyEnabled: true,
    slackNotifyEnabled: false,
    slackWebhookUrl: '',
    sidebarOpen: true,
    browserCurrentPath: '',
    currentAbortController: null,
    dbAvailable: true,
    dbCheckInterval: null,
    statusTimerInterval: null,
    statusStartTime: null,
    selectedImages: [],
    mediaRecorder: null,
    audioChunks: [],
    isRecording: false,
    currentAIProvider: 'auggie',
    availableProviders: ['auggie', 'openai'],
    currentOpenAIModel: 'gpt-5.2',
    availableOpenAIModels: ['gpt-5.2', 'gpt-5.2-chat-latest', 'gpt-5.1', 'gpt-5-mini', 'gpt-5-nano'],
    streamingMessageDiv: null
};

export const activeRequests = new Map();
export const pendingStreamPolls = new Map();

