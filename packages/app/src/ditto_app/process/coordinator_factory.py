"""摄取协调器工厂 — create_coordinator."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_data.models import Source
from ditto_data.services import (
    FreezeService,
    IngestionCursorService,
    IngestionLogService,
)
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService
from ditto_infra.foundation import logger

from ditto_app.process.ingestion_config import IngestionCoordinatorConfig
from ditto_app.process.ingestion_coordinator import (
    IngestionCoordinator,
    MarketServices,
)
from ditto_app.process.quality import QualityService


@dataclass(frozen=True)
class CoordinatorServices:
    """create_coordinator 所需的服务依赖聚合."""

    metadata_service: MetadataService
    market_service: MarketService
    market_write_service: MarketWriteService
    fundamental_service: FundamentalService
    capital_service: CapitalService
    macro_service: MacroService
    source_service: SourceService
    ingestion_log_service: IngestionLogService


@contextmanager
def create_coordinator(
    services: CoordinatorServices,
    source_name: str | Source,
    *,
    ingestion_cursor_service: IngestionCursorService | None = None,
    quality_service: QualityService | None = None,
    freeze_service: FreezeService | None = None,
) -> Iterator[IngestionCoordinator]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        services: 协调器所需服务依赖.
        source_name: 数据源名称.
        ingestion_cursor_service: IngestionCursorService 实例（可选）.
        quality_service: QualityService 实例（可选）.
        freeze_service: FreezeService 实例（可选）.

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
    data_source = services.source_service.get_source(source_key)

    # 获取 FRED 数据源（用于大宗商品数据）
    fred_source = None
    try:
        fred_source = services.source_service.get_source(Source.FRED)
    except Exception as e:
        logger.warning("FRED source not available", error=str(e))

    # 创建协调器
    coordinator = IngestionCoordinator(
        metadata_service=services.metadata_service,
        market_services=MarketServices(
            query=services.market_service,
            write=services.market_write_service,
        ),
        fundamental_service=services.fundamental_service,
        capital_service=services.capital_service,
        macro_service=services.macro_service,
        source=data_source,
        config=IngestionCoordinatorConfig(
            source_name=source_key.value,
            ingestion_log_service=services.ingestion_log_service,
            ingestion_cursor_service=ingestion_cursor_service,
            quality_service=quality_service,
            freeze_service=freeze_service,
            fred_source=fred_source,
        ),
    )

    yield coordinator


__all__ = [
    "CoordinatorServices",
    "create_coordinator",
]
