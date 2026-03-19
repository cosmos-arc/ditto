"""
摄取协调器工厂.

提供创建 IngestionCoordinator 实例的工厂函数，
处理运行时参数（如 source_name）的依赖注入。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_datahub.models import Source
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.services import IngestionCursorService, IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from ditto_infra.foundation import logger

from ditto_port.services.ingestion.coordinator import IngestionCoordinator
from ditto_port.services.ingestion.quality.service import QualityService


@contextmanager
def create_coordinator(  # noqa: PLR0913
    metadata_service: MetadataService,
    market_service: MarketService,
    fundamental_service: FundamentalService,
    capital_service: CapitalService,
    macro_service: MacroService,
    source_service: SourceService,
    ingestion_log_service: IngestionLogService,
    source_name: str | Source,
    ingestion_cursor_service: IngestionCursorService | None = None,
    quality_service: QualityService | None = None,
    freeze_manager: FreezeManager | None = None,
) -> Iterator[IngestionCoordinator]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        metadata_service: MetadataService 实例
        market_service: MarketService 实例
        fundamental_service: FundamentalService 实例
        capital_service: CapitalService 实例
        macro_service: MacroService 实例
        source_service: SourceService 实例
        ingestion_log_service: IngestionLogService 实例
        ingestion_cursor_service: IngestionCursorService 实例（可选）
        quality_service: QualityService 实例（可选）
        freeze_manager: FreezeManager 实例（可选）
        source_name: 数据源名称

    Yields:
        IngestionCoordinator: 协调器实例

    """
    # 支持 Source 枚举和字符串
    if isinstance(source_name, Source):
        source_key = source_name
    else:
        try:
            source_key = Source(source_name.lower())
        except ValueError as e:
            supported = [s.value for s in Source]
            raise ValueError(
                f"Unknown source: '{source_name}'. Supported sources: {supported}"
            ) from e

    # 获取主数据源
    data_source = source_service.get_source(source_key)

    # 获取 FRED 数据源（用于大宗商品数据）
    fred_source = None
    try:
        fred_source = source_service.get_source(Source.FRED)
    except Exception as e:
        logger.warning(f"FRED source not available: {e}")

    # 创建协调器
    coordinator = IngestionCoordinator(
        metadata_service=metadata_service,
        market_service=market_service,
        fundamental_service=fundamental_service,
        capital_service=capital_service,
        macro_service=macro_service,
        source=data_source,
        source_name=source_key.value,
        ingestion_log_service=ingestion_log_service,
        ingestion_cursor_service=ingestion_cursor_service,
        quality_service=quality_service,
        freeze_manager=freeze_manager,
        fred_source=fred_source,
    )

    yield coordinator
