import {
    checkDbStatus,
    checkDbStatusInBackground,
    showDbWarning,
    hideDbWarning,
    dismissDbWarning,
    retryDbConnection,
    isDbConnected,
    getDbError,
    resetDbState
} from '../modules/db.js';

describe('DB Module', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        resetDbState();
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('isDbConnected', () => {
        test('should return true by default', () => {
            expect(isDbConnected()).toBe(true);
        });

        test('should return false after checkDbStatus with disconnected status', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            checkDbStatus({ connected: false, error: 'Connection refused' }, true);
            expect(isDbConnected()).toBe(false);
        });
    });

    describe('getDbError', () => {
        test('should return null by default', () => {
            expect(getDbError()).toBeNull();
        });

        test('should return error after checkDbStatus with error', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            checkDbStatus({ connected: false, error: 'Connection refused' }, true);
            expect(getDbError()).toBe('Connection refused');
        });
    });

    describe('checkDbStatus', () => {
        test('should show warning when DB disconnected and history enabled', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            checkDbStatus({ connected: false, error: 'Error' }, true);
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner).not.toBeNull();
            expect(banner.style.display).toBe('flex');
        });

        test('should hide warning when DB connected', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            checkDbStatus({ connected: true }, true);
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner.style.display).toBe('none');
        });

        test('should hide warning when history disabled', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            checkDbStatus({ connected: false, error: 'Error' }, false);
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner.style.display).toBe('none');
        });

        test('should not show warning if already dismissed', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            dismissDbWarning();
            checkDbStatus({ connected: false, error: 'Error' }, true);
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner).toBeNull();
        });

        test('should do nothing if dbStatus is null', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            checkDbStatus(null, true);

            const banner = document.getElementById('dbStatusBanner');
            expect(banner).toBeNull();
        });
    });

    describe('checkDbStatusInBackground', () => {
        test('should show warning when DB disconnected', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';

            global.fetch = jest.fn(() => Promise.resolve({
                json: () => Promise.resolve({ connected: false, error: 'Connection refused' })
            }));

            await checkDbStatusInBackground();

            const banner = document.getElementById('dbStatusBanner');
            expect(banner).not.toBeNull();
            expect(banner.style.display).toBe('flex');
            expect(isDbConnected()).toBe(false);
        });

        test('should not show warning when DB connected', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';

            global.fetch = jest.fn(() => Promise.resolve({
                json: () => Promise.resolve({ connected: true })
            }));

            await checkDbStatusInBackground();

            const banner = document.getElementById('dbStatusBanner');
            expect(banner).toBeNull();
            expect(isDbConnected()).toBe(true);
        });

        test('should handle fetch error gracefully', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';

            global.fetch = jest.fn(() => Promise.reject(new Error('Network error')));

            await checkDbStatusInBackground();

            const banner = document.getElementById('dbStatusBanner');
            expect(banner).toBeNull();
        });
    });

    describe('showDbWarning', () => {
        test('should create banner with correct message', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner).not.toBeNull();
            expect(banner.querySelector('span').textContent).toContain('MongoDB connection issue');
        });

        test('should create banner with retry and dismiss buttons', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            
            const banner = document.getElementById('dbStatusBanner');
            const buttons = banner.querySelectorAll('button');
            expect(buttons.length).toBe(2);
        });

        test('should insert banner into chat-main', () => {
            document.body.innerHTML = '<div class="chat-main"><div>existing</div></div>';
            showDbWarning();
            
            const chatMain = document.querySelector('.chat-main');
            expect(chatMain.firstChild.id).toBe('dbStatusBanner');
        });

        test('should reuse existing banner', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            showDbWarning();
            
            const banners = document.querySelectorAll('#dbStatusBanner');
            expect(banners.length).toBe(1);
        });
    });

    describe('hideDbWarning', () => {
        test('should hide existing banner', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            hideDbWarning();
            
            const banner = document.getElementById('dbStatusBanner');
            expect(banner.style.display).toBe('none');
        });

        test('should do nothing if banner does not exist', () => {
            expect(() => hideDbWarning()).not.toThrow();
        });
    });

    describe('dismissDbWarning', () => {
        test('should hide banner and prevent future warnings', () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();
            dismissDbWarning();

            const banner = document.getElementById('dbStatusBanner');
            expect(banner.style.display).toBe('none');

            checkDbStatus({ connected: false, error: 'Error' }, true);
            expect(banner.style.display).toBe('none');
        });
    });

    describe('retryDbConnection', () => {
        beforeEach(() => {
            jest.useFakeTimers();
        });

        afterEach(() => {
            jest.useRealTimers();
        });

        test('should show retrying message and spin icon', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();

            global.fetch = jest.fn(() => new Promise(() => {}));

            retryDbConnection();

            const banner = document.getElementById('dbStatusBanner');
            const retryBtn = banner.querySelector('button');
            const retryIcon = retryBtn.querySelector('i');
            const messageSpan = banner.querySelector('span');

            expect(retryBtn.disabled).toBe(true);
            expect(retryIcon.classList.contains('retry-spin')).toBe(true);
            expect(messageSpan.textContent).toBe('Retrying connection...');
        });

        test('should hide banner when connection succeeds', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();

            global.fetch = jest.fn(() => Promise.resolve({
                json: () => Promise.resolve({ connected: true })
            }));

            const promise = retryDbConnection();
            jest.advanceTimersByTime(800);
            await promise;

            const banner = document.getElementById('dbStatusBanner');
            expect(banner.style.display).toBe('none');
            expect(isDbConnected()).toBe(true);
        });

        test('should show failed message when connection still fails', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();

            global.fetch = jest.fn(() => Promise.resolve({
                json: () => Promise.resolve({ connected: false, error: 'Still down' })
            }));

            const promise = retryDbConnection();
            jest.advanceTimersByTime(800);
            await promise;

            const banner = document.getElementById('dbStatusBanner');
            const messageSpan = banner.querySelector('span');
            const retryBtn = banner.querySelector('button');

            expect(messageSpan.textContent).toContain('Still MongoDB connection issue');
            expect(retryBtn.disabled).toBe(false);
        });

        test('should handle fetch error gracefully', async () => {
            document.body.innerHTML = '<div class="chat-main"></div>';
            showDbWarning();

            const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
            global.fetch = jest.fn(() => Promise.reject(new Error('Network error')));

            const promise = retryDbConnection();
            jest.advanceTimersByTime(800);
            await promise;

            const banner = document.getElementById('dbStatusBanner');
            const messageSpan = banner.querySelector('span');

            expect(messageSpan.textContent).toContain('Still MongoDB connection issue');
            expect(consoleSpy).toHaveBeenCalled();
            consoleSpy.mockRestore();
        });
    });

    describe('window exports', () => {
        test('should expose retryDbConnection on window', () => {
            expect(window.retryDbConnection).toBe(retryDbConnection);
        });

        test('should expose dismissDbWarning on window', () => {
            expect(window.dismissDbWarning).toBe(dismissDbWarning);
        });
    });
});

