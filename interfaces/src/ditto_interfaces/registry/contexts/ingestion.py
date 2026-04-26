"""摄入上下文工厂。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_app.command.quality_check import CheckDataQualityHandler
from ditto_app.process.ingestion.backfill_manager import BackfillManager
from ditto_app.process.ingestion.coordinator_factory import (
    CoordinatorServices,
    create_coordinator,
)
from ditto_app.process.ingestion.retry_manager import RetryManager
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_data.ingestion.freeze_service import FreezeService
from ditto_data.ingestion.ingestion_cursor_service import IngestionCursorService
from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService
from ditto_data.sources.exchange_transformers import ExchangeTransformers

from ditto_interfaces.registry.container import make_app_container
from ditto_interfaces.registry.contexts.bundle import IngestionBundle


@contextmanager
def create_ingestion_bundle(source: str = "tushare") -> Iterator[IngestionBundle]:
    """
    创建摄入上下文组合包（单容器）.

    解决 ARCH-004：替代嵌套的 create_ingestion_context + create_ingestion_log_context，
    确保单个 flow 只创建一个容器实例。

    Args:
        source: 数据源名称

    Yields:
        IngestionBundle: 包含协调器、管理器和查询 facade

    Example:
        with create_ingestion_bundle() as bundle:
            result = bundle.coordinator.ingest(...)
            bundle.metadata_facade.is_trading_day(...)

    """
    container = make_app_container()
    try:
        # 获取所有服务
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        market_write_service = container.get(MarketWriteService)
        fundamental_service = container.get(FundamentalService)
        capital_service = container.get(CapitalService)
        macro_service = container.get(MacroService)
        source_service = container.get(SourceService)
        ingestion_log_service = container.get(IngestionLogService)
        ingestion_cursor_service = container.get(IngestionCursorService)
        exchange_transformers = container.get(ExchangeTransformers)
        quality_checker = container.get(CheckDataQualityHandler)
        freeze_service = container.get(FreezeService)

        # 创建协调器
        with create_coordinator(
            CoordinatorServices(
                metadata_service=metadata_service,
                market_service=market_service,
                market_write_service=market_write_service,
                fundamental_service=fundamental_service,
                capital_service=capital_service,
                macro_service=macro_service,
                source_service=source_service,
                ingestion_log_service=ingestion_log_service,
            ),
            source_name=source,
            ingestion_cursor_service=ingestion_cursor_service,
            quality_checker=quality_checker,
            freeze_service=freeze_service,
        ) as coordinator:
            # 创建管理器
            backfill_manager = BackfillManager(
                coordinator=coordinator,
                metadata_service=metadata_service,
                ingestion_log_service=ingestion_log_service,
            )
            retry_manager = RetryManager(
                coordinator=coordinator,
                ingestion_log_service=ingestion_log_service,
                source=source,
            )
            # 创建查询 facade
            metadata_facade = MetadataQueryFacade(metadata_service=metadata_service)

            yield IngestionBundle(
                coordinator=coordinator,
                backfill_manager=backfill_manager,
                retry_manager=retry_manager,
                metadata_facade=metadata_facade,
                exchange_transformers=exchange_transformers,
            )
    finally:
        container.close()
