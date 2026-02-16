"""CLI 上下文管理（使用 IngestionBundle）."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ditto_port.cli.executor import CLIExecutor
from ditto_port.registry.contexts import create_ingestion_bundle


@contextmanager
def create_cli_host() -> Generator[Any, None, None]:
    """
    CLI Host - 仿照 .NET Generic Host 模式.

    管理整个 CLI 应用的生命周期：
    - 创建容器
    - 初始化所有组件
    - 优雅关闭

    Note: 此函数保留用于向后兼容。
    推荐使用 create_executor() 获取完整的 CLIExecutor。

    Yields:
        dishka 同步容器实例

    """
    # 委托给 create_ingestion_bundle 以保持一致性
    with create_ingestion_bundle() as bundle:
        yield bundle


@contextmanager
def create_executor(
    source_name: str = "tushare",
    data_root: Path | None = None,
) -> Generator[CLIExecutor, None, None]:
    """
    创建 CLI 执行器（使用 DI 和工厂模式）.

    通过 create_ingestion_bundle 获取完整的依赖包，
    然后创建 CLIExecutor。

    Args:
        source_name: 数据源名称，默认为 "tushare"
        data_root: 数据根目录（预留参数，未来用于显式传递）

    Yields:
        CLIExecutor: 已初始化的执行器实例

    Note:
        data_root 参数目前暂未使用，ConfigProvider 仍通过
        环境变量 DITTO_DATA_ROOT 获取配置。后续重构可改为
        显式参数传递。

    """
    with create_ingestion_bundle(source=source_name) as bundle:
        yield CLIExecutor(
            coordinator=bundle.coordinator,
            backfill_manager=bundle.backfill_manager,
        )
