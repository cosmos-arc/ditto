"""摄取协调器工厂 — create_coordinator."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_data.ingestion.freeze_service import FreezeService
from ditto_data.ingestion.ingestion_cursor_service import IngestionCursorService
from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.models import Source
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionServices,
    MarketServices,
    SourceFetchers,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol


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
    quality_checker: QualityCheckerProtocol | None = None,
    freeze_service: FreezeService | None = None,
) -> Generator[IngestionCoordinator, None, None]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        services: 协调器所需服务依赖.
        source_name: 数据源名称.
        ingestion_cursor_service: IngestionCursorService 实例（可选）.
        quality_checker: QualityCheckerProtocol 实例（可选）.
        freeze_service: FreezeService 实例（可选）.

    Yields:
        IngestionCoordinator: 协调器实例

    """
    if isinstance(source_name, Source):
        source_key = source_name
    else:
        try:
            source_key = Source(source_name.lower())
        except ValueError as e:
            supported = [s.value for s in Source]
            raise AppProcessError(
                f"Unknown source: '{source_name}'. Supported sources: {supported}",
                field="source_name",
                value=source_name,
                supported=supported,
            ) from e

    data_source = services.source_service.tushare

    fred_source = services.source_service.fred
    if fred_source is not None:
        logger.debug("FRED source available for commodity data")

    coordinator = IngestionCoordinator(
        services=IngestionServices(
            metadata=services.metadata_service,
            market=MarketServices(
                query=services.market_service,
                write=services.market_write_service,
            ),
            fundamental=services.fundamental_service,
            capital=services.capital_service,
            macro=services.macro_service,
        ),
        fetchers=SourceFetchers(
            metadata=data_source,
            market=data_source,
            fundamental=data_source,
            capital=data_source,
            macro=data_source,
        ),
        fred_source=fred_source,
        config=IngestionCoordinatorConfig(
            source_name=source_key.value,
            ingestion_log_service=services.ingestion_log_service,
            ingestion_cursor_service=ingestion_cursor_service,
            quality_checker=quality_checker,
            freeze_service=freeze_service,
        ),
    )

    yield coordinator


__all__ = [
    "CoordinatorServices",
    "create_coordinator",
]
