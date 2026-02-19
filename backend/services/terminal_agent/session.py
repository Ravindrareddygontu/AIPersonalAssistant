import os
import pty
import time
import fcntl
import struct
import select
import termios
import logging
import threading
from subprocess import Popen
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.terminal_agent.base import TerminalAgentProvider

log = logging.getLogger('terminal_agent.session')


class TerminalSession:

    def __init__(self, provider: 'TerminalAgentProvider', workspace: str, model: Optional[str] = None):
        self.provider = provider
        self.workspace = os.path.expanduser(workspace)
        self.model = model or provider.config.default_model
        self.process: Optional[Popen] = None
        self.master_fd: Optional[int] = None
        self.initialized: bool = False
        self.in_use: bool = False
        self.last_message: str = ''
        self.last_response: str = ''
        self.lock = threading.RLock()
        self._created_at = time.time()

    @property
    def session_key(self) -> str:
        return f"{self.provider.name}:{self.workspace}:{self.model or 'default'}"

    def start(self) -> bool:
        if self.process and self.is_alive():
            log.warning(f"[{self.provider.name}] Session already running")
            return True

        try:
            master_fd, slave_fd = pty.openpty()

            winsize = struct.pack('HHHH', 24, 80, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

            self._set_nonblocking(master_fd)

            cmd = self.provider.get_command(self.workspace, self.model)
            env = self.provider.get_env()

            log.info(f"[{self.provider.name}] Starting session: {' '.join(cmd)}")

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
            self.master_fd = master_fd
            return True

        except Exception as e:
            log.exception(f"[{self.provider.name}] Failed to start session: {e}")
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
        log.info(f"[{self.provider.name}] Cleaning up session")
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        self.initialized = False

    def _handle_terminal_queries(self, chunk: str) -> None:
        if not self.master_fd:
            return
        try:
            if '\x1b[6n' in chunk:
                os.write(self.master_fd, b'\x1b[24;1R')
            if '\x1b[c' in chunk:
                os.write(self.master_fd, b'\x1b[?62;c')
            if '\x1b]10;?' in chunk:
                os.write(self.master_fd, b'\x1b]10;rgb:0000/0000/0000\x1b\\')
            if '\x1b]11;?' in chunk:
                os.write(self.master_fd, b'\x1b]11;rgb:ffff/ffff/ffff\x1b\\')
        except OSError:
            pass

    def _check_update_prompt(self, output: str) -> bool:
        return 'Update available!' in output or 'Press enter to continue' in output

    def wait_for_prompt(self, timeout: float = 60.0) -> Tuple[bool, str]:
        if not self.master_fd:
            return False, ''

        start = time.time()
        output = ''
        patterns = self.provider.get_prompt_patterns()
        update_prompt_handled = False

        while time.time() - start < timeout:
            ready = select.select([self.master_fd], [], [], 0.5)[0]
            if ready:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    output += chunk

                    self._handle_terminal_queries(chunk)

                    if not update_prompt_handled and self._check_update_prompt(output):
                        log.info(f"[{self.provider.name}] Update prompt detected, sending skip")
                        time.sleep(0.3)
                        os.write(self.master_fd, b'2\n')
                        update_prompt_handled = True
                        output = ''
                        continue

                    for pattern in patterns:
                        if pattern.search(output):
                            log.info(f"[{self.provider.name}] Prompt detected")
                            return True, output
                except (BlockingIOError, OSError):
                    pass

        log.warning(f"[{self.provider.name}] Timeout waiting for prompt")
        return False, output

    def drain_output(self, timeout: float = 0.3) -> str:
        if not self.master_fd:
            return ''

        output = ''
        start = time.time()
        while time.time() - start < timeout:
            ready = select.select([self.master_fd], [], [], 0.1)[0]
            if ready:
                try:
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        output += chunk
                    else:
                        break
                except (BlockingIOError, OSError):
                    break
            else:
                break
        return output

    def write(self, data: bytes) -> bool:
        if not self.master_fd:
            return False
        try:
            os.write(self.master_fd, data)
            return True
        except (BrokenPipeError, OSError) as e:
            log.error(f"[{self.provider.name}] Write error: {e}")
            return False

    def read(self, size: int = 8192) -> str:
        if not self.master_fd:
            return ''
        try:
            return os.read(self.master_fd, size).decode('utf-8', errors='ignore')
        except (BlockingIOError, OSError):
            return ''

