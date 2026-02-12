import os
import pty
import time
import signal
import select
import subprocess
import threading

_sessions = {}
_lock = threading.Lock()


class AuggieSession:
    def __init__(self, workspace):
        self.workspace = workspace
        self.process = None
        self.master_fd = None
        self.last_used = time.time()
        self.lock = threading.Lock()
        self.initialized = False
        self.last_response = ""
        self.last_message = ""

    def start(self):
        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.update({'TERM': 'xterm-256color', 'AUGMENT_WORKSPACE': self.workspace, 'COLUMNS': '200', 'LINES': '100'})
        self.process = subprocess.Popen(['auggie'], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                                        cwd=self.workspace, env=env, preexec_fn=os.setsid)
        os.close(slave_fd)
        self.master_fd = master_fd
        self.last_used = time.time()
        return self.master_fd

    def is_alive(self):
        return self.process and self.process.poll() is None

    def cleanup(self):
        if self.process:
            try:
                os.kill(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=2)
            except:
                try:
                    os.kill(self.process.pid, signal.SIGKILL)
                except:
                    pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
        self.process = self.master_fd = None
        self.initialized = False

    def wait_for_prompt(self, timeout=15):
        start, output = time.time(), ""
        while time.time() - start < timeout:
            if select.select([self.master_fd], [], [], 0.3)[0]:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    output += chunk
                    if '›' in chunk:
                        time.sleep(0.5)
                        self.drain_output()
                        return True, output
                except OSError:
                    break
        return False, output

    def drain_output(self, timeout=0.5):
        end = time.time() + timeout
        while time.time() < end:
            if select.select([self.master_fd], [], [], 0.1)[0]:
                try:
                    os.read(self.master_fd, 8192)
                except:
                    break
            else:
                break


class SessionManager:
    @staticmethod
    def get_or_create(workspace):
        with _lock:
            if workspace in _sessions and _sessions[workspace].is_alive():
                _sessions[workspace].last_used = time.time()
                return _sessions[workspace], False
            if workspace in _sessions:
                _sessions[workspace].cleanup()
            _sessions[workspace] = AuggieSession(workspace)
            return _sessions[workspace], True

    @staticmethod
    def cleanup_old():
        with _lock:
            now = time.time()
            for ws in [w for w, s in _sessions.items() if now - s.last_used > 600]:
                _sessions[ws].cleanup()
                del _sessions[ws]

    @staticmethod
    def reset(workspace):
        with _lock:
            if workspace in _sessions:
                _sessions[workspace].cleanup()
                del _sessions[workspace]

