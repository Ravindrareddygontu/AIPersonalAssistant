const { app, BrowserWindow, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

app.commandLine.appendSwitch('no-sandbox');

let mainWindow;
let flaskProcess;

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

    return new Promise((resolve) => setTimeout(resolve, 2000));
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200, height: 800, minWidth: 600, minHeight: 500,
        title: 'Augment Chat', icon: path.join(__dirname, 'static', 'icon.png'),
        webPreferences: { nodeIntegration: false, contextIsolation: true },
        backgroundColor: '#0d1117', autoHideMenuBar: true
    });
    mainWindow.loadURL('http://localhost:5000');
    mainWindow.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
    mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(async () => {
    await startFlaskServer();
    createWindow();
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

app.on('before-quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGTERM'); } catch (e) {}
});

app.on('quit', () => {
    if (flaskProcess && !flaskProcess.killed) try { flaskProcess.kill('SIGKILL'); } catch (e) {}
});
