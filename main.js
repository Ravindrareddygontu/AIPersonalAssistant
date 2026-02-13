const { app, BrowserWindow, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

app.commandLine.appendSwitch('no-sandbox');

let mainWindow;
let splashWindow;
let flaskProcess;

function createSplashWindow() {
    splashWindow = new BrowserWindow({
        width: 400, height: 350,
        frame: false,
        resizable: false,
        center: true,
        skipTaskbar: false,
        icon: path.join(__dirname, 'static', 'icon.png'),
        backgroundColor: '#0d1117',
        webPreferences: { nodeIntegration: false, contextIsolation: true }
    });
    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    splashWindow.on('closed', () => { splashWindow = null; });
}

function startFlaskServer() {
    const venvPython = path.join(__dirname, 'venv', 'bin', 'python');
    const appPath = path.join(__dirname, 'backend', 'app.py');

    flaskProcess = spawn(venvPython, [appPath], {
        cwd: __dirname,
        env: { ...process.env, FLASK_ENV: 'production' },
        stdio: ['pipe', 'pipe', 'pipe']
    });

    const handlePipeError = (stream, name) => {
        if (stream) {
            stream.on('error', (err) => { if (err.code !== 'EPIPE') console.error(`Flask ${name} error:`, err); });
            if (name !== 'stdin') stream.on('data', (data) => console.log(`Flask: ${data}`));
        }
    };
    handlePipeError(flaskProcess.stdout, 'stdout');
    handlePipeError(flaskProcess.stderr, 'stderr');
    handlePipeError(flaskProcess.stdin, 'stdin');

    flaskProcess.on('error', (err) => console.error('Failed to start Flask server:', err));
    flaskProcess.on('close', (code) => { console.log(`Flask process exited with code ${code}`); flaskProcess = null; });

    return new Promise((resolve) => setTimeout(resolve, 2500));
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200, height: 800, minWidth: 600, minHeight: 500,
        title: 'Augment Chat', icon: path.join(__dirname, 'static', 'icon.png'),
        webPreferences: { nodeIntegration: false, contextIsolation: true },
        backgroundColor: '#0d1117', autoHideMenuBar: true,
        show: false
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
    mainWindow.on('closed', () => { mainWindow = null; });

    return mainWindow;
}

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
        const check = () => {
            attempts++;
            const req = http.get(url, (res) => {
                if (res.statusCode === 200) {
                    console.log('Server is ready!');
                    resolve(true);
                } else {
                    retry();
                }
            });
            req.on('error', () => retry());
            req.setTimeout(500, () => { req.destroy(); retry(); });
        };
        const retry = () => {
            if (attempts < maxAttempts) {
                setTimeout(check, 200);
            } else {
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

    // Wait for server to respond
    console.log('Waiting for Flask server...');
    await waitForServer('http://localhost:5000');

    // Create hidden main window
    createWindow();

    // Load the URL
    mainWindow.loadURL('http://localhost:5000');

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
                mainWindow.loadURL('http://localhost:5000');
            }
        }, 1000);
    });

    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

app.on('before-quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGTERM'); } catch (e) {}
});

app.on('quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGKILL'); } catch (e) {}
});
