const { app, BrowserWindow, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Disable sandbox for Linux compatibility
app.commandLine.appendSwitch('no-sandbox');

let mainWindow;
let flaskProcess;

// Start Flask server
function startFlaskServer() {
    const venvPython = path.join(__dirname, 'venv', 'bin', 'python');
    const appPath = path.join(__dirname, 'app.py');
    
    flaskProcess = spawn(venvPython, [appPath], {
        cwd: __dirname,
        env: { ...process.env, FLASK_ENV: 'production' }
    });

    flaskProcess.stdout.on('data', (data) => {
        console.log(`Flask: ${data}`);
    });

    flaskProcess.stderr.on('data', (data) => {
        console.log(`Flask: ${data}`);
    });

    flaskProcess.on('error', (err) => {
        console.error('Failed to start Flask server:', err);
    });

    // Wait for Flask to start
    return new Promise((resolve) => {
        setTimeout(resolve, 2000);
    });
}

// Create the main window
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 600,
        minHeight: 500,
        title: 'Augment Chat',
        icon: path.join(__dirname, 'static', 'icon.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true
        },
        backgroundColor: '#0d1117',
        autoHideMenuBar: true
    });

    // Load the Flask app
    mainWindow.loadURL('http://localhost:5000');

    // Open external links in browser
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// App ready
app.whenReady().then(async () => {
    await startFlaskServer();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

// Quit when all windows are closed
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Clean up Flask process on quit
app.on('before-quit', () => {
    if (flaskProcess) {
        flaskProcess.kill('SIGTERM');
    }
});

app.on('quit', () => {
    if (flaskProcess) {
        flaskProcess.kill('SIGKILL');
    }
});

