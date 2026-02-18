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
_cleanup_thread = None
_cleanup_stop_event = threading.Event()

# Configuration for stale process cleanup
STALE_PROCESS_AGE_MINUTES = 30  # Kill auggie processes older than this
CLEANUP_INTERVAL_SECONDS = 300  # Run cleanup every 5 minutes
MAX_AUGGIE_PROCESSES = 3  # Maximum number of auggie processes allowed


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
        self.in_use = False  # Track if terminal is actively being used (streaming)

    def start(self):
        import os
        import pty
        import time
        import struct
        import fcntl
        import termios

        master_fd, slave_fd = pty.openpty()

        # Properly set PTY window size
        rows = 100
        cols = 200
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        env = os.environ.copy()

        nvm_bin = '/home/dell/.nvm/versions/node/v22.22.0/bin'
        if nvm_bin not in env.get('PATH', ''):
            env['PATH'] = nvm_bin + ':' + env.get('PATH', '/usr/bin:/bin')

        env.update({
            'TERM': 'xterm-256color',
            'AUGMENT_WORKSPACE': self.workspace
        })

        auggie_cmd = 'auggie'
        for path in [
            '/home/dell/.nvm/versions/node/v22.22.0/bin/auggie',
            os.path.expanduser('~/.nvm/versions/node/v22.22.0/bin/auggie'),
            '/usr/local/bin/auggie',
            '/usr/bin/auggie'
        ]:
            if os.path.exists(path):
                auggie_cmd = path
                break

        cmd = [auggie_cmd]
        auggie_model_id = None
        if self.model:
            auggie_model_id = get_auggie_model_id(self.model)
            cmd.extend(['-m', auggie_model_id])

        log.info(f"[SESSION] Starting auggie from: {auggie_cmd}, workspace: {self.workspace}, model: {self.model} (auggie_id: {auggie_model_id})")

        self.process = subprocess.Popen(
            cmd,
            stdin = slave_fd,
            stdout = slave_fd,
            stderr = slave_fd,
            cwd = self.workspace,
            env = env,
            preexec_fn = os.setsid,
            close_fds = True
        )

        os.close(slave_fd)

        # Set window size on master_fd as well (some apps read from master side)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        # Set master_fd to non-blocking mode for proper async reads
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

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

    def wait_for_prompt(self, timeout=60, status_callback=None):
        start, output = time.time(), ""
        prompt_seen = False
        indexing_complete = False
        indexing_started = False
        last_status_time = 0

        log.info(f"[SESSION] Waiting for prompt and indexing (timeout={timeout}s)...")

        def send_status(msg):
            nonlocal last_status_time
            now = time.time()
            # Throttle status updates to every 0.5 seconds
            if status_callback and (now - last_status_time) >= 0.5:
                status_callback(msg)
                last_status_time = now

        while time.time() - start < timeout:
            if select.select([self.master_fd], [], [], 0.3)[0]:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    output += chunk
                    log.debug(f"[SESSION] Received chunk: {repr(chunk[:100])}")

                    # Check for prompt
                    if '›' in chunk or '>' in chunk:
                        prompt_seen = True

                    # Check for indexing status
                    if 'Indexing...' in chunk or 'Indexing' in output:
                        if not indexing_started:
                            log.info(f"[SESSION] Indexing started")
                        indexing_started = True
                        elapsed = time.time() - start
                        send_status(f"Indexing codebase... ({elapsed:.0f}s)")

                    if 'Indexing complete' in chunk or 'Indexing complete' in output:
                        indexing_complete = True
                        log.info(f"[SESSION] Indexing complete after {time.time()-start:.1f}s")
                        send_status("Indexing complete!")

                    # Ready when: prompt seen AND (indexing complete OR no indexing started after 5s)
                    if prompt_seen:
                        if indexing_complete:
                            log.info(f"[SESSION] Ready (indexing complete) after {time.time()-start:.1f}s")
                            time.sleep(0.5)
                            self.drain_output()
                            return True, output
                        elif not indexing_started and (time.time() - start) > 5:
                            # No indexing seen after 5s, probably already indexed
                            log.info(f"[SESSION] Ready (no indexing needed) after {time.time()-start:.1f}s")
                            time.sleep(0.5)
                            self.drain_output()
                            return True, output

                except OSError as e:
                    log.error(f"[SESSION] OSError reading: {e}")
                    break
            else:
                # No data, but send periodic status if indexing
                if indexing_started and not indexing_complete:
                    elapsed = time.time() - start
                    send_status(f"Indexing codebase... ({elapsed:.0f}s)")

        # Timeout - but if prompt was seen, still try to proceed
        if prompt_seen:
            log.warning(f"[SESSION] Timeout but prompt seen, proceeding anyway")
            self.drain_output()
            return True, output

        log.warning(f"[SESSION] Timeout waiting for prompt. Output so far: {repr(output[:200])}")
        return False, output

    def drain_output(self, timeout=1.0):
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


def _is_app_spawned_process(pid):
    try:
        env_path = f'/proc/{pid}/environ'
        if os.path.exists(env_path):
            with open(env_path, 'rb') as f:
                env_data = f.read().decode('utf-8', errors='ignore')
                # Environment variables are null-separated
                return 'AUGMENT_WORKSPACE=' in env_data
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return False


def _get_auggie_processes():
    try:
        # Use ps to get auggie processes with start time
        result = subprocess.run(
            ['ps', '-eo', 'pid,etimes,cmd', '--no-headers'],
            capture_output=True, text=True, timeout=5
        )
        processes = []
        for line in result.stdout.strip().split('\n'):
            if 'auggie' in line and 'grep' not in line:
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    try:
                        pid = int(parts[0])
                        elapsed_seconds = int(parts[1])  # Time since process started
                        cmd = parts[2]

                        # Only consider processes spawned by this app
                        # Skip user-started auggie processes in their terminal
                        if not _is_app_spawned_process(pid):
                            log.debug(f"[CLEANUP] Skipping PID {pid}: not app-spawned (user terminal)")
                            continue

                        processes.append({
                            'pid': pid,
                            'elapsed_seconds': elapsed_seconds,
                            'elapsed_minutes': elapsed_seconds / 60,
                            'cmd': cmd
                        })
                    except (ValueError, IndexError):
                        continue
        return processes
    except Exception as e:
        log.warning(f"[CLEANUP] Failed to get auggie processes: {e}")
        return []


def _get_tracked_pids():
    with _lock:
        return {s.process.pid for s in _sessions.values() if s.process and s.is_alive()}


def cleanup_stale_auggie_processes(force_aggressive=False):
    tracked_pids = _get_tracked_pids()
    processes = _get_auggie_processes()

    if not processes:
        return 0

    # Log tracked vs all processes for debugging
    all_pids = [p['pid'] for p in processes]
    log.info(f"[CLEANUP] All auggie PIDs: {all_pids}, Tracked PIDs: {tracked_pids}")

    killed_count = 0
    current_time = time.time()

    # Sort by elapsed time (oldest first)
    processes.sort(key=lambda p: p['elapsed_seconds'], reverse=True)

    # Get only untracked processes for cleanup consideration
    untracked_processes = [p for p in processes if p['pid'] not in tracked_pids]

    if not untracked_processes:
        log.debug("[CLEANUP] No untracked processes to clean up")
        return 0

    for proc in untracked_processes:
        pid = proc['pid']
        elapsed_minutes = proc['elapsed_minutes']

        should_kill = False
        reason = ""

        # Kill if process is older than threshold
        if elapsed_minutes > STALE_PROCESS_AGE_MINUTES:
            should_kill = True
            reason = f"older than {STALE_PROCESS_AGE_MINUTES} minutes ({elapsed_minutes:.1f}m)"

        # Kill if we have too many UNTRACKED auggie processes (keep newest ones)
        # Only count untracked processes toward the limit - tracked ones are actively managed
        elif len(untracked_processes) > MAX_AUGGIE_PROCESSES:
            # Sort untracked by age (oldest first) and kill the oldest ones
            if pid in [p['pid'] for p in untracked_processes[:-MAX_AUGGIE_PROCESSES]]:
                should_kill = True
                reason = f"too many untracked auggie processes ({len(untracked_processes)} untracked, {len(processes)} total)"

        # Aggressive mode: kill anything not tracked that's older than 10 minutes
        elif force_aggressive and elapsed_minutes > 10:
            should_kill = True
            reason = f"aggressive cleanup ({elapsed_minutes:.1f}m old)"

        if should_kill:
            try:
                log.info(f"[CLEANUP] Killing stale auggie process PID {pid}: {reason}")
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
                # Check if still running, force kill if necessary
                try:
                    os.kill(pid, 0)  # Check if process exists
                    os.kill(pid, signal.SIGKILL)
                    log.info(f"[CLEANUP] Force killed PID {pid}")
                except ProcessLookupError:
                    pass  # Already dead
                killed_count += 1
            except ProcessLookupError:
                pass  # Process already gone
            except PermissionError:
                log.warning(f"[CLEANUP] Permission denied killing PID {pid}")
            except Exception as e:
                log.warning(f"[CLEANUP] Error killing PID {pid}: {e}")

    if killed_count > 0:
        log.info(f"[CLEANUP] Cleaned up {killed_count} stale auggie processes")

    return killed_count


def _cleanup_thread_func():
    log.info("[CLEANUP] Background cleanup thread started")
    while not _cleanup_stop_event.is_set():
        try:
            cleanup_stale_auggie_processes()
        except Exception as e:
            log.error(f"[CLEANUP] Error in cleanup thread: {e}")

        # Wait for interval or stop event
        _cleanup_stop_event.wait(CLEANUP_INTERVAL_SECONDS)

    log.info("[CLEANUP] Background cleanup thread stopped")


def start_cleanup_thread():
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_cleanup_thread_func, daemon=True)
        _cleanup_thread.start()
        log.info("[CLEANUP] Started background cleanup thread")


class SessionManager:
    @staticmethod
    def get_or_create(workspace, model=None):
        # Ensure cleanup thread is running
        start_cleanup_thread()

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
                # Don't delete sessions that have an active terminal open (in_use)
                if _sessions[ws].in_use:
                    log.info(f"[CLEANUP] Skipping session {ws}: terminal is in use")
                    continue
                # Don't delete sessions where the process is still alive - user may return
                # Only delete sessions where the process has died
                if _sessions[ws].is_alive():
                    log.info(f"[CLEANUP] Skipping session {ws}: process still alive (PID: {_sessions[ws].process.pid})")
                    continue
                log.info(f"[CLEANUP] Cleaning up dead session {ws}")
                _sessions[ws].cleanup()
                del _sessions[ws]

        # Also clean up any orphaned OS processes
        cleanup_stale_auggie_processes()

    @staticmethod
    def reset(workspace):
        with _lock:
            if workspace in _sessions:
                # Don't reset if terminal is actively in use
                if _sessions[workspace].in_use:
                    log.warning(f"[RESET] Cannot reset session {workspace}: terminal is in use")
                    return False
                _sessions[workspace].cleanup()
                del _sessions[workspace]

        # Aggressively clean up stale processes on reset
        cleanup_stale_auggie_processes(force_aggressive=True)
        return True
