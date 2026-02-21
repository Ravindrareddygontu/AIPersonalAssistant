const { app, BrowserWindow, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

// Load .env file
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    envContent.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
            const [key, ...valueParts] = trimmed.split('=');
            if (key && valueParts.length > 0) {
                let value = valueParts.join('=');
                // Remove surrounding quotes if present
                if ((value.startsWith('"') && value.endsWith('"')) ||
                    (value.startsWith("'") && value.endsWith("'"))) {
                    value = value.slice(1, -1);
                }
                process.env[key] = value;
            }
        }
    });
}

app.commandLine.appendSwitch('no-sandbox');

// Disable hardware acceleration to reduce CPU usage
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-software-rasterizer');

// Log file for debugging when running from desktop icon
const logFile = path.join(__dirname, 'electron.log');
function log(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] ${message}\n`;
    console.log(message);
    try {
        fs.appendFileSync(logFile, logMessage);
    } catch (e) { /* ignore */ }
}

let mainWindow;
let splashWindow;
let flaskProcess;
let slackBotProcess;
let logsTerminalProcess = null;

function createSplashWindow() {
    splashWindow = new BrowserWindow({
        width: 400, height: 350,
        frame: false,
        resizable: false,
        center: true,
        skipTaskbar: false,
        icon: path.join(__dirname, 'static', 'icon-round.png'),
        transparent: true,
        backgroundColor: '#00000000',
        webPreferences: { nodeIntegration: false, contextIsolation: true }
    });
    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    splashWindow.on('closed', () => { splashWindow = null; });
}

function startFlaskServer() {
    const venvPython = path.join(__dirname, 'venv', 'bin', 'python');
    const appPath = path.join(__dirname, 'backend', 'app.py');

    log(`Starting Flask server...`);
    log(`__dirname: ${__dirname}`);
    log(`Python path: ${venvPython}`);
    log(`App path: ${appPath}`);

    // Check if files exist
    if (!fs.existsSync(venvPython)) {
        log(`ERROR: Python not found at ${venvPython}`);
        return Promise.resolve();
    }
    if (!fs.existsSync(appPath)) {
        log(`ERROR: app.py not found at ${appPath}`);
        return Promise.resolve();
    }
    log(`Files verified, spawning Python process...`);

    flaskProcess = spawn(venvPython, [appPath], {
        cwd: __dirname,
        env: { ...process.env, FLASK_ENV: 'production' },
        stdio: ['pipe', 'pipe', 'pipe']
    });

    const handlePipeError = (stream, name) => {
        if (stream) {
            stream.on('error', (err) => { if (err.code !== 'EPIPE') log(`Backend ${name} error: ${err}`); });
            if (name !== 'stdin') stream.on('data', (data) => log(data.toString().trimEnd()));
        }
    };
    handlePipeError(flaskProcess.stdout, 'stdout');
    handlePipeError(flaskProcess.stderr, 'stderr');
    handlePipeError(flaskProcess.stdin, 'stdin');

    flaskProcess.on('error', (err) => log(`Failed to start Flask server: ${err}`));
    flaskProcess.on('close', (code) => { log(`Flask process exited with code ${code}`); flaskProcess = null; });

    return new Promise((resolve) => setTimeout(resolve, 2500));
}

function startSlackBot() {
    const venvPython = path.join(__dirname, 'venv', 'bin', 'python');
    const slackScript = path.join(__dirname, 'start_slack.py');

    // Check if Slack tokens are configured
    if (!process.env.SLACK_BOT_TOKEN || !process.env.SLACK_APP_TOKEN) {
        log('Slack bot not started: SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set');
        return;
    }

    if (!fs.existsSync(slackScript)) {
        log(`Slack script not found at ${slackScript}`);
        return;
    }

    log('Starting Slack bot...');
    slackBotProcess = spawn(venvPython, [slackScript, '--mode=socket'], {
        cwd: __dirname,
        env: { ...process.env },
        stdio: ['pipe', 'pipe', 'pipe']
    });

    const handlePipeError = (stream, name) => {
        if (stream) {
            stream.on('error', (err) => { if (err.code !== 'EPIPE') log(`Slack bot ${name} error: ${err}`); });
            if (name !== 'stdin') stream.on('data', (data) => log(`[SLACK] ${data.toString().trimEnd()}`));
        }
    };
    handlePipeError(slackBotProcess.stdout, 'stdout');
    handlePipeError(slackBotProcess.stderr, 'stderr');
    handlePipeError(slackBotProcess.stdin, 'stdin');

    slackBotProcess.on('error', (err) => log(`Failed to start Slack bot: ${err}`));
    slackBotProcess.on('close', (code) => { log(`Slack bot exited with code ${code}`); slackBotProcess = null; });
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200, height: 800, minWidth: 600, minHeight: 500,
        title: 'Digistant', icon: path.join(__dirname, 'static', 'icon-round.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        backgroundColor: '#0d1117', autoHideMenuBar: true,
        show: false
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
    mainWindow.on('closed', () => { mainWindow = null; });

    return mainWindow;
}

// Open terminal with live logs
function openLogsTerminal() {
    // Kill existing terminal if open
    if (logsTerminalProcess && !logsTerminalProcess.killed) {
        try { logsTerminalProcess.kill(); } catch (e) {}
    }

    // Command to tail the journalctl logs for this app
    const logCommand = `journalctl --user -f -n 100 | grep -E "CHAT|SESSION|RENDERER|INFO:|ERROR:|WARNING:"`;

    // Try different terminal emulators (gnome-terminal.real first for Ubuntu systems where gnome-terminal wrapper may be broken)
    const terminals = [
        { cmd: 'gnome-terminal.real', args: ['--', 'bash', '-c', `${logCommand}; read -p "Press Enter to close..."`] },
        { cmd: 'gnome-terminal', args: ['--', 'bash', '-c', `${logCommand}; read -p "Press Enter to close..."`] },
        { cmd: 'xfce4-terminal', args: ['-e', `bash -c '${logCommand}; read -p "Press Enter to close..."'`] },
        { cmd: 'konsole', args: ['-e', 'bash', '-c', `${logCommand}; read -p "Press Enter to close..."`] },
        { cmd: 'xterm', args: ['-e', `bash -c '${logCommand}; read -p "Press Enter to close..."'`] },
    ];

    for (const term of terminals) {
        try {
            // Check if terminal exists
            const which = require('child_process').spawnSync('which', [term.cmd]);
            if (which.status === 0) {
                log(`Opening logs in ${term.cmd}...`);
                logsTerminalProcess = spawn(term.cmd, term.args, {
                    detached: true,
                    stdio: 'ignore'
                });
                logsTerminalProcess.unref();
                return { success: true, terminal: term.cmd };
            }
        } catch (e) {
            continue;
        }
    }

    log('No terminal emulator found');
    return { success: false, error: 'No terminal emulator found' };
}

// IPC handler for opening logs terminal
ipcMain.handle('open-logs-terminal', async () => {
    return openLogsTerminal();
});

// IPC handler for resetting the session
ipcMain.handle('reset-session', async () => {
    try {
        const response = await fetch('http://localhost:5001/api/chat/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        return { success: response.ok };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// IPC handler for selecting image files
ipcMain.handle('select-images', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        title: 'Select Images',
        properties: ['openFile', 'multiSelections'],
        filters: [
            { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'] }
        ]
    });

    if (result.canceled || !result.filePaths || result.filePaths.length === 0) {
        return { canceled: true, paths: [] };
    }

    // Return array of objects with path and name
    const images = result.filePaths.map(filePath => ({
        path: filePath,
        name: path.basename(filePath)
    }));

    log(`Selected ${images.length} images: ${images.map(i => i.path).join(', ')}`);
    return { canceled: false, images };
});

function closeSplashAndShowMain() {
    if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.close();
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
    }
}

function waitForServer(url, maxAttempts = 50) {
    return new Promise((resolve) => {
        let attempts = 0;
        let resolved = false;
        const check = () => {
            if (resolved) return;
            attempts++;
            const req = http.get(url, (res) => {
                if (resolved) return;
                if (res.statusCode === 200) {
                    resolved = true;
                    console.log('Server is ready!');
                    resolve(true);
                } else {
                    retry();
                }
            });
            req.on('error', () => { if (!resolved) retry(); });
            req.setTimeout(500, () => { req.destroy(); if (!resolved) retry(); });
        };
        const retry = () => {
            if (resolved) return;
            if (attempts < maxAttempts) {
                setTimeout(check, 200);
            } else {
                resolved = true;
                console.log('Server timeout, proceeding anyway');
                resolve(false);
            }
        };
        check();
    });
}

app.whenReady().then(async () => {
    // Show splash immediately
    createSplashWindow();

    // Start Flask server (don't await)
    startFlaskServer();

    // Start Slack bot in background
    startSlackBot();

    // Wait for server to respond
    console.log('Waiting for Flask server...');
    await waitForServer('http://localhost:5001');

    // Create hidden main window
    createWindow();

    // Clear cache to ensure fresh JS/CSS files are loaded
    await mainWindow.webContents.session.clearCache();

    // Load the URL
    mainWindow.loadURL('http://localhost:5001');

    // Forward all renderer console logs to terminal with colors
    mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
        const levelNames = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
        const levelName = levelNames[level] || 'LOG';
        const RED = '\x1b[91m';
        const YELLOW = '\x1b[93m';
        const RESET = '\x1b[0m';
        let output = `[RENDERER ${levelName}] ${message}`;
        if (level >= 3) {
            output = `${RED}${output}${RESET}`;
        } else if (level >= 2) {
            output = `${YELLOW}${output}${RESET}`;
        }
        console.log(output);
    });

    // When page finishes loading, close splash and show main
    mainWindow.webContents.on('did-finish-load', () => {
        console.log('Page loaded, showing main window');
        setTimeout(() => {
            closeSplashAndShowMain();
        }, 300); // Small delay for smoother transition
    });

    // Handle load failures - retry
    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        console.log('Load failed:', errorDescription, '- retrying...');
        setTimeout(() => {
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.loadURL('http://localhost:5001');
            }
        }, 1000);
    });

    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

app.on('before-quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGTERM'); } catch (e) {}
    if (slackBotProcess && !slackBotProcess.killed) try { slackBotProcess.kill('SIGTERM'); } catch (e) {}
});

app.on('quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGKILL'); } catch (e) {}
    if (slackBotProcess && !slackBotProcess.killed) try { slackBotProcess.kill('SIGKILL'); } catch (e) {}
});
