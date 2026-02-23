import os
import time
import select
import logging
from typing import List, Optional, Tuple, TYPE_CHECKING

from backend.services.base_session import BasePtySession

if TYPE_CHECKING:
    from backend.services.terminal_agent.base import TerminalAgentProvider

log = logging.getLogger('terminal_agent.session')


class TerminalSession(BasePtySession):

    def __init__(self, provider: 'TerminalAgentProvider', workspace: str, model: Optional[str] = None, session_id: Optional[str] = None):
        super().__init__(workspace, model or provider.config.default_model, session_id)
        self.provider = provider
        self._created_at = time.time()

    @property
    def session_key(self) -> str:
        return f"{self.provider.name}:{self.workspace}:{self.model or 'default'}"

    def get_command(self) -> List[str]:
        return self.provider.get_command(self.workspace, self.model, self.session_id)

    def get_env(self) -> dict:
        return self.provider.get_env()

    def get_prompt_patterns(self) -> List:
        return self.provider.get_prompt_patterns()

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
        patterns = self.get_prompt_patterns()
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

