"""摄入上下文工厂。"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_app.process.ingestion import BackfillManager, create_coordinator
from ditto_app.process.quality import QualityService
from ditto_datahub.services import (
    FreezeService,
    IngestionCursorService,
    IngestionLogService,
)
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from ditto_datahub.sources import ExchangeTransformers

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
        IngestionBundle: 包含所有摄入服务、协调器和回补管理器

    Example:
        with create_ingestion_bundle() as bundle:
            result = bundle.coordinator.ingest(...)
            bundle.metadata_service.is_trading_day(...)

    """
    container = make_app_container()
    try:
        # 获取所有服务
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        fundamental_service = container.get(FundamentalService)
        capital_service = container.get(CapitalService)
        macro_service = container.get(MacroService)
        source_service = container.get(SourceService)
        ingestion_log_service = container.get(IngestionLogService)
        ingestion_cursor_service = container.get(IngestionCursorService)
        exchange_transformers = container.get(ExchangeTransformers)
        quality_service = container.get(QualityService)
        freeze_service = container.get(FreezeService)

        # 创建协调器
        with create_coordinator(
            metadata_service=metadata_service,
            market_service=market_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_service=source_service,
            ingestion_log_service=ingestion_log_service,
            ingestion_cursor_service=ingestion_cursor_service,
            quality_service=quality_service,
            freeze_service=freeze_service,
            source_name=source,
        ) as coordinator:
            # 创建回补管理器
            backfill_manager = BackfillManager(
                coordinator=coordinator,
                metadata_service=metadata_service,
                ingestion_log_service=ingestion_log_service,
            )
            yield IngestionBundle(
                metadata_service=metadata_service,
                market_service=market_service,
                fundamental_service=fundamental_service,
                capital_service=capital_service,
                macro_service=macro_service,
                source_service=source_service,
                ingestion_log_service=ingestion_log_service,
                exchange_transformers=exchange_transformers,
                coordinator=coordinator,
                backfill_manager=backfill_manager,
            )
    finally:
        container.close()
