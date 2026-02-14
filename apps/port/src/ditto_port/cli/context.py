"""CLI 上下文管理（使用 dishka 同步容器）."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from ditto_datahub.models import Source
from ditto_datahub.services import IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService

from ditto_port.cli.executor import CLIExecutor
from ditto_port.registry.container import make_app_container


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
    container = make_app_container()
    try:
        yield container
    finally:
        # 优雅关闭
        container.close()


@contextmanager
def create_executor():
    """
    创建 CLI 执行器（使用 DI 和工厂模式）.

    通过 DI 容器获取所需的 Services，然后使用 CLIExecutor.create() 工厂方法创建执行器。

    Yields:
        CLIExecutor: 已初始化的执行器实例

    """
    with create_cli_host() as container:
        # 从容器获取所需的 Services
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        fundamental_service = container.get(FundamentalService)
        capital_service = container.get(CapitalService)
        macro_service = container.get(MacroService)
        source_service = container.get(SourceService)
        ingestion_log_service = container.get(IngestionLogService)
        # 使用工厂方法创建 executor，自动处理 coordinator 和 backfill_manager 的初始化
        with CLIExecutor.create(
            metadata_service=metadata_service,
            market_service=market_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_service=source_service,
            ingestion_log_service=ingestion_log_service,
            source_name=Source.TUSHARE,
        ) as executor:
            yield executor
