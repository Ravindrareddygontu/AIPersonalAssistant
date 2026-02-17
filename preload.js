const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
    // Open a terminal window showing live Python/Flask logs
    openLogsTerminal: () => ipcRenderer.invoke('open-logs-terminal'),

    // Reset the auggie session
    resetSession: () => ipcRenderer.invoke('reset-session'),

    // Select image files using native dialog (returns array of absolute paths)
    selectImages: () => ipcRenderer.invoke('select-images'),
});

