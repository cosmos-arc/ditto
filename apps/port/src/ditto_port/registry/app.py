"""
基础设施组件注册.

注册应用级单例组件：Observability、SQLitePool、XDGPaths 等。
"""

import os
from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_foundation.observability import init, shutdown

__all__ = ["AppProvider"]


class AppProvider(Provider):
    """基础设施组件 Provider."""

    scope = Scope.APP

    @provide
    def observability(self) -> Iterator[None]:
        """
        初始化 Observability，应用级单例.

        生命周期：容器启动时初始化，容器关闭时调用 shutdown().
        """
        env = os.getenv("DITTO_ENV", "development")

        init(
            service_name="ditto-server",
            environment=env,
            log_level="DEBUG" if env == "development" else "INFO",
            log_dir="logs",  # 内部使用 XDGPaths.state_subdir("logs") 解析
            pytest_running=False,
            assertions_enabled=False,
            verbose_logging=(env == "development"),
        )

        yield

        # 容器关闭时调用 shutdown
        shutdown()
