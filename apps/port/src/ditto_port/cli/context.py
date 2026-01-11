"""CLI 上下文管理."""

from typing import Any

from ditto_datahub import DataHub

from ditto_port.cli.executor import CLIExecutor


def ensure_executor(ctx: Any) -> None:
    """确保执行器已初始化."""
    if "executor" not in ctx.obj:
        data_root = ctx.obj.get("data_root")

        # 创建 DataHub
        hub = DataHub(data_root=data_root)

        # 创建 AppContext
        app_ctx = _AppContext(hub=hub, source=hub.sources)

        # 创建执行器
        executor = CLIExecutor(app_ctx)

        ctx.obj["executor"] = executor
        ctx.obj["app_ctx"] = app_ctx
        ctx.obj["hub"] = hub


class _AppContext:
    """CLI 应用上下文."""

    def __init__(self, hub: DataHub, source: Any) -> None:
        """初始化."""
        self.hub = hub
        self.source = source
