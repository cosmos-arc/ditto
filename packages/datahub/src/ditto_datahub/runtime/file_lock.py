"""Cross-platform file lock manager using filelock library."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ditto_foundation import logger

try:
    from filelock import FileLock, Timeout
except ImportError as e:
    raise ImportError(
        "The 'filelock' package is required. Install with: pip install filelock"
    ) from e


class LockAcquisitionError(Exception):
    """Raised when lock acquisition fails due to timeout."""

    def __init__(
        self,
        message: str,
        lock_name: str = "",
        timeout_seconds: float = 0,
    ) -> None:
        super().__init__(message)
        self.lock_name = lock_name
        self.timeout_seconds = timeout_seconds


class FileLockManager:
    """Cross-platform file lock manager based on open-source filelock library."""

    def __init__(self, lock_dir: Path) -> None:
        """
        初始化文件锁管理器.

        Args:
            lock_dir: 锁文件存储目录

        """
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "file_lock_manager_init",
            event="file_lock_init",
            lock_dir=str(self.lock_dir),
        )

    @contextmanager
    def acquire(self, name: str, timeout: float = 30.0) -> Iterator[None]:
        """
        获取文件锁的上下文管理器.

        Args:
            name: 锁名称
            timeout: 超时时间(秒)

        Raises:
            LockAcquisitionError: 获取锁超时

        """
        lock_path = self.lock_dir / f"{name}.lock"
        lock = FileLock(lock_path, timeout=timeout)

        logger.debug(
            "file_lock_acquire_start",
            event="file_lock_acquire_start",
            lock_name=name,
            timeout=timeout,
        )

        try:
            with lock:
                logger.debug(
                    "file_lock_acquired",
                    event="file_lock_acquired",
                    lock_name=name,
                )
                yield
        except Timeout as e:
            logger.error(
                "file_lock_timeout",
                event="file_lock_timeout",
                lock_name=name,
                timeout=timeout,
            )
            raise LockAcquisitionError(
                f"Failed to acquire lock '{name}' within {timeout}s",
                lock_name=name,
                timeout_seconds=timeout,
            ) from e
