import os
import pty
import time
import fcntl
import struct
import select
import signal
import termios
import logging
import threading
from abc import ABC, abstractmethod
from subprocess import Popen
from typing import Optional, Tuple, List

log = logging.getLogger('session.base')


class BasePtySession(ABC):
    DEFAULT_ROWS = 24
    DEFAULT_COLS = 80

    def __init__(self, workspace: str, model: Optional[str] = None, session_id: Optional[str] = None):
        self.workspace = os.path.expanduser(workspace)
        self.model = model
        self.session_id = session_id
        self.process: Optional[Popen] = None
        self.master_fd: Optional[int] = None
        self.initialized: bool = False
        self.in_use: bool = False
        self.last_message: str = ''
        self.last_response: str = ''
        self.last_used: float = time.time()
        self.lock = threading.RLock()

    @abstractmethod
    def get_command(self) -> List[str]:
        pass

    @abstractmethod
    def get_env(self) -> dict:
        pass

    @abstractmethod
    def get_prompt_patterns(self) -> List:
        pass

    def get_window_size(self) -> Tuple[int, int]:
        return self.DEFAULT_ROWS, self.DEFAULT_COLS

    def start(self) -> bool:
        if self.process and self.is_alive():
            log.warning(f"[{self.__class__.__name__}] Session already running")
            return True

        try:
            master_fd, slave_fd = pty.openpty()
            rows, cols = self.get_window_size()
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
            self._set_nonblocking(master_fd)

            cmd = self.get_command()
            env = self.get_env()

            log.info(f"[{self.__class__.__name__}] Starting: {' '.join(cmd)}")

            self.process = Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.workspace,
                env=env,
                start_new_session=True,
            )
            os.close(slave_fd)

            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            self.master_fd = master_fd
            self.last_used = time.time()

            log.info(f"[{self.__class__.__name__}] Started PID: {self.process.pid}")
            return True

        except Exception as e:
            log.exception(f"[{self.__class__.__name__}] Failed to start: {e}")
            self.cleanup()
            return False

    def _set_nonblocking(self, fd: int) -> None:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def is_alive(self) -> bool:
        if not self.process:
            return False
        return self.process.poll() is None

    def cleanup(self) -> None:
        log.info(f"[{self.__class__.__name__}] Cleaning up session")
        if self.process:
            try:
                os.kill(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=2)
            except Exception:
                try:
                    os.kill(self.process.pid, signal.SIGKILL)
                except Exception:
                    pass
            self.process = None

        if self.master_fd:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        self.initialized = False

    def drain_output(self, timeout: float = 1.0) -> str:
        if not self.master_fd:
            return ''

        output = ''
        end = time.time() + timeout
        while time.time() < end:
            if select.select([self.master_fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        output += chunk
                    else:
                        break
                except (BlockingIOError, OSError):
                    break
            else:
                time.sleep(0.05)
                if not select.select([self.master_fd], [], [], 0.05)[0]:
                    break
        return output

    def write(self, data: bytes) -> bool:
        if not self.master_fd:
            return False
        try:
            os.write(self.master_fd, data)
            return True
        except (BrokenPipeError, OSError) as e:
            log.error(f"[{self.__class__.__name__}] Write error: {e}")
            return False

    def read(self, size: int = 8192) -> str:
        if not self.master_fd:
            return ''
        try:
            return os.read(self.master_fd, size).decode('utf-8', errors='ignore')
        except (BlockingIOError, OSError):
            return ''

