"""CLI 上下文管理（使用 dishka 同步容器）."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from dishka import make_container
from ditto_datahub import DataHub
from ditto_datahub.models import Source

from ditto_port.cli.executor import CLIExecutor
from ditto_port.registry import (
    ConfigProvider,
    CoreProvider,
    DataHubProvider,
    DataSourcesProvider,
    DomainServiceProvider,
)


@contextmanager
def create_cli_host() -> Generator[Any, None, None]:
    """
    CLI Host - 仿照 .NET Generic Host 模式（同步版本）.

    管理整个 CLI 应用的生命周期：
    - 创建容器
    - 初始化所有组件
    - 优雅关闭

    Yields:
        dishka 同步容器实例

    """
    # 创建同步容器
    container = make_container(
        ConfigProvider(),
        CoreProvider(),
        DomainServiceProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
    try:
        yield container
    finally:
        # 优雅关闭
        container.close()


@contextmanager
def create_executor():
    """
    创建 CLI 执行器（使用 DI 和工厂模式）.

    通过 DI 容器获取 DataHub，然后使用 CLIExecutor.create() 工厂方法创建执行器。

    Yields:
        CLIExecutor: 已初始化的执行器实例

    """
    with create_cli_host() as container:
        # 从容器获取 DataHub（同步）
        hub = container.get(DataHub)
        # 使用工厂方法创建 executor，自动处理 coordinator 和 backfill_manager 的初始化
        with CLIExecutor.create(hub=hub, source_name=Source.TUSHARE) as executor:
            yield executor
