import os
import pty
import time
import signal
import select
import subprocess
import threading
import logging

from backend.config import get_auggie_model_id

log = logging.getLogger('session')

_sessions = {}
_lock = threading.Lock()


class AuggieSession:
    def __init__(self, workspace, model=None):
        self.workspace = workspace
        self.model = model
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

        # Find auggie - try common locations
        auggie_cmd = 'auggie'
        for path in ['/home/dell/.nvm/versions/node/v20.20.0/bin/auggie',
                     os.path.expanduser('~/.nvm/versions/node/v20.20.0/bin/auggie'),
                     '/usr/local/bin/auggie', '/usr/bin/auggie']:
            if os.path.exists(path):
                auggie_cmd = path
                break

        # Build command with model if specified
        cmd = [auggie_cmd]
        auggie_model_id = None
        if self.model:
            auggie_model_id = get_auggie_model_id(self.model)
            cmd.extend(['-m', auggie_model_id])

        log.info(f"[SESSION] Starting auggie from: {auggie_cmd}, workspace: {self.workspace}, model: {self.model} (auggie_id: {auggie_model_id})")
        self.process = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                                        cwd=self.workspace, env=env, preexec_fn=os.setsid)
        os.close(slave_fd)
        self.master_fd = master_fd
        self.last_used = time.time()
        log.info(f"[SESSION] Process started with PID: {self.process.pid}")
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

    def wait_for_prompt(self, timeout=30):
        start, output = time.time(), ""
        log.info(f"[SESSION] Waiting for prompt (timeout={timeout}s)...")
        while time.time() - start < timeout:
            if select.select([self.master_fd], [], [], 0.3)[0]:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    output += chunk
                    log.debug(f"[SESSION] Received chunk: {repr(chunk[:100])}")
                    # Check for various prompt indicators
                    if '›' in chunk or '>' in chunk or 'auggie' in chunk.lower():
                        log.info(f"[SESSION] Prompt detected after {time.time()-start:.1f}s")
                        time.sleep(0.5)
                        self.drain_output()
                        return True, output
                except OSError as e:
                    log.error(f"[SESSION] OSError reading: {e}")
                    break
        log.warning(f"[SESSION] Timeout waiting for prompt. Output so far: {repr(output[:200])}")
        return False, output

    def drain_output(self, timeout=1.0):
        """Drain all pending output from the terminal buffer"""
        end = time.time() + timeout
        drained = 0
        while time.time() < end:
            if select.select([self.master_fd], [], [], 0.1)[0]:
                try:
                    data = os.read(self.master_fd, 8192)
                    drained += len(data)
                except:
                    break
            else:
                # No more data available, wait a bit and check again
                time.sleep(0.1)
                if not select.select([self.master_fd], [], [], 0.1)[0]:
                    break  # Still no data, we're done
        log.info(f"[SESSION] drain_output: drained {drained} bytes")
        return drained


class SessionManager:
    @staticmethod
    def get_or_create(workspace, model=None):
        with _lock:
            if workspace in _sessions and _sessions[workspace].is_alive():
                # If model changed, restart the session
                if model and _sessions[workspace].model != model:
                    log.info(f"[SESSION] Model changed from {_sessions[workspace].model} to {model}, restarting session")
                    _sessions[workspace].cleanup()
                    _sessions[workspace] = AuggieSession(workspace, model)
                    return _sessions[workspace], True
                _sessions[workspace].last_used = time.time()
                return _sessions[workspace], False
            if workspace in _sessions:
                _sessions[workspace].cleanup()
            _sessions[workspace] = AuggieSession(workspace, model)
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

