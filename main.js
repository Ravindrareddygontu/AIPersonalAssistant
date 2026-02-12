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
        env: { ...process.env, FLASK_ENV: 'production' },
        stdio: ['pipe', 'pipe', 'pipe']
    });

    // Handle stdout with error handling for EPIPE
    if (flaskProcess.stdout) {
        flaskProcess.stdout.on('data', (data) => {
            console.log(`Flask: ${data}`);
        });
        flaskProcess.stdout.on('error', (err) => {
            if (err.code !== 'EPIPE') {
                console.error('Flask stdout error:', err);
            }
        });
    }

    // Handle stderr with error handling for EPIPE
    if (flaskProcess.stderr) {
        flaskProcess.stderr.on('data', (data) => {
            console.log(`Flask: ${data}`);
        });
        flaskProcess.stderr.on('error', (err) => {
            if (err.code !== 'EPIPE') {
                console.error('Flask stderr error:', err);
            }
        });
    }

    // Handle stdin with error handling for EPIPE
    if (flaskProcess.stdin) {
        flaskProcess.stdin.on('error', (err) => {
            if (err.code !== 'EPIPE') {
                console.error('Flask stdin error:', err);
            }
        });
    }

    flaskProcess.on('error', (err) => {
        console.error('Failed to start Flask server:', err);
    });

    flaskProcess.on('close', (code) => {
        console.log(`Flask process exited with code ${code}`);
        flaskProcess = null;
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
    if (flaskProcess && !flaskProcess.killed) {
        try {
            flaskProcess.kill('SIGTERM');
        } catch (err) {
            // Ignore errors if process already exited
        }
    }
});

app.on('quit', () => {
    if (flaskProcess && !flaskProcess.killed) {
        try {
            flaskProcess.kill('SIGKILL');
        } catch (err) {
            // Ignore errors if process already exited
        }
    }
});

