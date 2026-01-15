"""CLI 上下文管理."""

import threading
from contextlib import contextmanager
from typing import Any

from ditto_datahub import DataHub

from ditto_port.cli.executor import CLIExecutor

# 模块级单例
_hub: DataHub | None = None
_hub_lock = threading.Lock()


def get_hub(data_root: str | None = None) -> DataHub:
    """
    获取应用级 DataHub 单例.

    Args:
        data_root: 数据根目录（首次调用时设置）

    Returns:
        DataHub 实例（同一进程内返回同一实例）

    """
    global _hub  # noqa: PLW0603 - singleton pattern requires global state
    if _hub is None:
        with _hub_lock:
            if _hub is None:
                _hub = DataHub(data_root=data_root)
    return _hub


@contextmanager
def create_executor(data_root: str | None):
    """
    创建 CLI 执行器上下文管理器.

    自动管理 DataHub 生命周期，确保资源正确释放.

    Args:
        data_root: 数据根目录

    Yields:
        CLIExecutor: 可用的执行器实例

    """
    hub = get_hub(data_root)
    try:
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
    finally:
        # hub 由 atexit 清理，这里不关闭
        pass


class _AppContext:
    """CLI 应用上下文."""

    def __init__(self, hub: DataHub, source: Any) -> None:
        """初始化."""
        self.hub = hub
        self.source = source
