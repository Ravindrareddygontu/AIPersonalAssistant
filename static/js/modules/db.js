let dbConnected = true;
let dbError = null;
let bannerDismissed = false;
let onReconnectCallback = null;

export function resetDbState() {
    dbConnected = true;
    dbError = null;
    bannerDismissed = false;
}

export function setOnReconnectCallback(callback) {
    onReconnectCallback = callback;
}

export function isDbConnected() {
    return dbConnected;
}

export function getDbError() {
    return dbError;
}

export function checkDbStatus(dbStatus, historyEnabled) {
    if (!dbStatus) return;

    dbConnected = dbStatus.connected;
    dbError = dbStatus.error || null;

    if (!dbConnected && historyEnabled && !bannerDismissed) {
        showDbWarning(dbError);
    } else {
        hideDbWarning();
    }
}

function getOrCreateBanner() {
    let banner = document.getElementById('dbStatusBanner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'dbStatusBanner';
        banner.className = 'db-status-banner';
        const chatMain = document.querySelector('.chat-main');
        if (chatMain) {
            chatMain.insertBefore(banner, chatMain.firstChild);
        }
    }
    return banner;
}

export function showDbSuccess() {
    const banner = getOrCreateBanner();
    banner.className = 'db-status-banner db-status-success';
    banner.innerHTML = `
        <i class="fas fa-check-circle"></i>
        <span>MongoDB connected</span>
    `;
    banner.style.display = 'flex';

    setTimeout(() => {
        banner.style.display = 'none';
        banner.className = 'db-status-banner';
    }, 2000);
}

export function showDbWarning(error) {
    const banner = getOrCreateBanner();
    banner.className = 'db-status-banner';
    banner.innerHTML = `
        <i class="fas fa-exclamation-triangle"></i>
        <span>MongoDB connection issue – your chats won't be stored</span>
        <button onclick="window.retryDbConnection()" title="Retry connection">
            <i class="fas fa-sync-alt"></i>
        </button>
        <button onclick="window.dismissDbWarning()" title="Dismiss">
            <i class="fas fa-times"></i>
        </button>
    `;
    banner.style.display = 'flex';
}

export function hideDbWarning() {
    const banner = document.getElementById('dbStatusBanner');
    if (banner) {
        banner.style.display = 'none';
    }
}

export function dismissDbWarning() {
    bannerDismissed = true;
    hideDbWarning();
}

export async function checkDbStatusInBackground() {
    try {
        const response = await fetch('/api/db-status');
        const status = await response.json();

        dbConnected = status.connected;
        dbError = status.error || null;

        if (!dbConnected && !bannerDismissed) {
            showDbWarning(dbError);
        }
    } catch (error) {
        console.error('[DB] Failed to check connection:', error);
    }
}

export async function retryDbConnection() {
    const banner = document.getElementById('dbStatusBanner');
    const retryBtn = banner?.querySelector('button');
    const retryIcon = retryBtn?.querySelector('i');
    const messageSpan = banner?.querySelector('span');
    const retryFailedMessage = 'Still MongoDB connection issue – your chats won\'t be stored';

    if (retryBtn && retryIcon) {
        retryBtn.disabled = true;
        retryIcon.classList.add('retry-spin');
    }
    if (messageSpan) {
        messageSpan.textContent = 'Retrying connection...';
    }

    const minDelay = new Promise(resolve => setTimeout(resolve, 800));

    try {
        const [response] = await Promise.all([fetch('/api/db-status'), minDelay]);
        const status = await response.json();

        dbConnected = status.connected;
        dbError = status.error || null;

        if (dbConnected) {
            showDbSuccess();
            bannerDismissed = false;
            if (onReconnectCallback) {
                onReconnectCallback();
            }
        } else {
            if (retryBtn && retryIcon) {
                retryBtn.disabled = false;
                retryIcon.classList.remove('retry-spin');
            }
            if (messageSpan) {
                messageSpan.textContent = retryFailedMessage;
            }
        }
    } catch (error) {
        console.error('[DB] Failed to check connection:', error);
        await minDelay;
        if (retryBtn && retryIcon) {
            retryBtn.disabled = false;
            retryIcon.classList.remove('retry-spin');
        }
        if (messageSpan) {
            messageSpan.textContent = retryFailedMessage;
        }
    }
}

window.retryDbConnection = retryDbConnection;
window.dismissDbWarning = dismissDbWarning;

