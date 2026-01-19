"""
并发控制通用能力.

本模块提供跨项目的并发控制基础设施，包括文件锁等通用技术组件。
这些是纯粹的工程技术实现，不包含任何业务逻辑或领域特定规则。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ditto_foundation.observability import logger

try:
    from filelock import FileLock, Timeout
except ImportError as e:
    raise ImportError(
        "The 'filelock' package is required. Install with: pixi add filelock"
    ) from e


__all__ = ["FileLockManager", "LockAcquisitionError"]


class LockAcquisitionError(Exception):
    """
    获取锁失败异常.

    当锁获取超时时抛出此异常。

    Attributes:
        message: 错误消息
        lock_name: 锁名称
        timeout_seconds: 超时时间(秒)

    """

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
    """
    跨平台文件锁管理器.

    基于开源 filelock 库实现，提供跨平台的文件锁能力。
    适用于进程间同步、资源互斥访问等通用并发控制场景。

    Example:
        >>> manager = FileLockManager(Path("/tmp/locks"))
        >>> with manager.acquire("my_resource"):
        ...     # 临界区代码
        ...     pass

    """

    def __init__(self, lock_dir: Path) -> None:
        """
        初始化文件锁管理器.

        Args:
            lock_dir: 锁文件存储目录

        """
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "File lock manager initialized",
            event="file_lock_init_complete",
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
            "Attempting to acquire file lock",
            event="file_lock_acquire_start",
            lock_name=name,
            timeout=timeout,
        )

        try:
            with lock:
                logger.debug(
                    "File lock acquired",
                    event="file_lock_acquired",
                    lock_name=name,
                )
                yield
        except Timeout as e:
            logger.error(
                "File lock acquisition timeout",
                event="file_lock_timeout",
                lock_name=name,
                timeout=timeout,
            )
            raise LockAcquisitionError(
                f"Failed to acquire lock '{name}' within {timeout}s",
                lock_name=name,
                timeout_seconds=timeout,
            ) from e
