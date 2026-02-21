import logging
from contextlib import contextmanager
from filelock import FileLock, Timeout

log = logging.getLogger('storage.locking')

DEFAULT_LOCK_TIMEOUT = 10


@contextmanager
def file_lock(path: str, timeout: float = DEFAULT_LOCK_TIMEOUT):
    lock_path = f"{path}.lock"
    lock = FileLock(lock_path, timeout=timeout)
    try:
        lock.acquire()
        yield
    except Timeout:
        log.error(f"Failed to acquire lock for {path} within {timeout}s")
        raise
    finally:
        lock.release()


class LockManager:
    def __init__(self, timeout: float = DEFAULT_LOCK_TIMEOUT):
        self.timeout = timeout
        self._locks = {}

    def get_lock(self, path: str) -> FileLock:
        if path not in self._locks:
            self._locks[path] = FileLock(f"{path}.lock", timeout=self.timeout)
        return self._locks[path]

    @contextmanager
    def lock(self, path: str):
        lock = self.get_lock(path)
        try:
            lock.acquire()
            yield
        except Timeout:
            log.error(f"Failed to acquire lock for {path}")
            raise
        finally:
            lock.release()

