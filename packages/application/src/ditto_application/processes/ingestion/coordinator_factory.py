"""摄取协调器工厂 — create_coordinator."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, cast

from ditto_data.catalog import DataCatalogReader, DataCatalogWriter
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.ingestion.freeze_store import FreezeStore
from ditto_data.ingestion.ingestion_cursor_store import (
    IngestionCursorStore,
)
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.lineage import DataLineageRecorder
from ditto_data.models import Source
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_accessor import SourceAccessor
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionServices,
    MarketServices,
    SourceFetchers,
)
from ditto_application.processes.ingestion.date_range import list_ingestion_dates
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.source_selection import (
    AUTO_SOURCE_NAME,
    AutoSourceIngestionCoordinator,
    IngestionCoordinatorLike,
)


class SourceRegistryLike(Protocol):
    """Source registry port used by the ingestion composition factory."""

    def get[FetcherT](self, name: str, protocol: type[FetcherT]) -> FetcherT:
        """Return a source implementation registered for ``name`` + ``protocol``."""
        ...


@dataclass(frozen=True)
class CoordinatorServices:
    """create_coordinator 所需的服务依赖聚合."""

    metadata_service: MetadataService
    market_service: MarketService
    market_write_service: MarketWriteService
    fundamental_store: FundamentalStore
    capital_store: CapitalStore
    macro_service: MacroService
    source_accessor: SourceAccessor
    ingestion_log_store: IngestionLogStore
    source_registry: SourceRegistryLike | None = None


@dataclass(frozen=True)
class CoordinatorRuntimeContext:
    """Optional runtime ports for ingestion coordinator composition."""

    ingestion_cursor_store: IngestionCursorStore | None = None
    quality_checker: QualityCheckerProtocol | None = None
    freeze_store: FreezeStore | None = None
    lineage_recorder: DataLineageRecorder | None = None
    catalog_reader: DataCatalogReader | None = None
    catalog_writer: DataCatalogWriter | None = None
    source_fallback_policy_reader: CatalogSourceFallbackPolicyReader | None = None


def _registered_source_or_default[FetcherT](
    *,
    registry: SourceRegistryLike | None,
    source_name: str,
    protocol: type[FetcherT],
    default_source: FetcherT,
) -> FetcherT:
    """Return the registered source for a protocol, falling back to Tushare."""
    if registry is None:
        return default_source
    try:
        return registry.get(source_name, protocol)
    except ValueError:
        return default_source


def _fred_macro_fetcher(
    services: CoordinatorServices,
    default_source: MacroFetcher,
) -> MacroFetcher:
    """Resolve FRED as a runtime macro fetcher when it is configured."""
    registry = services.source_registry
    if registry is not None:
        try:
            return registry.get(Source.FRED.value, MacroFetcher)
        except ValueError as exc:
            if services.source_accessor.fred is None:
                raise AppProcessError(
                    "Source 'fred' is not configured for MacroFetcher",
                    field="source_name",
                    value=Source.FRED.value,
                    supported=[Source.TUSHARE.value],
                ) from exc

    fred_source = services.source_accessor.fred
    if fred_source is None:
        raise AppProcessError(
            "Source 'fred' is not configured for MacroFetcher",
            field="source_name",
            value=Source.FRED.value,
            supported=[Source.TUSHARE.value],
        )
    return cast("MacroFetcher", fred_source)


def _has_registered_fetcher[FetcherT](
    *,
    registry: SourceRegistryLike | None,
    source_name: str,
    protocol: type[FetcherT],
) -> bool:
    """Return whether a fetcher is explicitly registered for source/protocol."""
    if registry is None:
        return False
    try:
        registry.get(source_name, protocol)
    except ValueError:
        return False
    return True


def _auto_source_keys(services: CoordinatorServices) -> tuple[Source, ...]:
    """Return concrete sources that can participate in source=auto."""
    source_keys = [Source.TUSHARE]
    if services.source_accessor.fred is not None or _has_registered_fetcher(
        registry=services.source_registry,
        source_name=Source.FRED.value,
        protocol=MacroFetcher,
    ):
        source_keys.append(Source.FRED)
    return tuple(source_keys)


def _source_fetchers_for(
    services: CoordinatorServices,
    source_key: Source,
) -> SourceFetchers:
    """Build domain fetchers for the requested runtime source."""
    default_source = services.source_accessor.tushare
    non_macro_source_name = (
        Source.TUSHARE.value if source_key is Source.FRED else source_key.value
    )
    macro_fetcher = (
        _fred_macro_fetcher(services, default_source)
        if source_key is Source.FRED
        else _registered_source_or_default(
            registry=services.source_registry,
            source_name=source_key.value,
            protocol=MacroFetcher,
            default_source=default_source,
        )
    )

    return SourceFetchers(
        metadata=_registered_source_or_default(
            registry=services.source_registry,
            source_name=non_macro_source_name,
            protocol=MetadataFetcher,
            default_source=default_source,
        ),
        market=_registered_source_or_default(
            registry=services.source_registry,
            source_name=non_macro_source_name,
            protocol=MarketFetcher,
            default_source=default_source,
        ),
        fundamental=_registered_source_or_default(
            registry=services.source_registry,
            source_name=non_macro_source_name,
            protocol=FundamentalFetcher,
            default_source=default_source,
        ),
        capital=_registered_source_or_default(
            registry=services.source_registry,
            source_name=non_macro_source_name,
            protocol=CapitalFetcher,
            default_source=default_source,
        ),
        macro=macro_fetcher,
    )


def _build_coordinator(
    services: CoordinatorServices,
    source_key: Source,
    *,
    runtime: CoordinatorRuntimeContext,
) -> IngestionCoordinator:
    """Build one source-consistent ingestion coordinator."""
    fred_source = services.source_accessor.fred
    if fred_source is not None:
        logger.debug("FRED source available for commodity data")

    return IngestionCoordinator(
        services=IngestionServices(
            metadata=services.metadata_service,
            market=MarketServices(
                query=services.market_service,
                write=services.market_write_service,
            ),
            fundamental=services.fundamental_store,
            capital=services.capital_store,
            macro=services.macro_service,
        ),
        fetchers=_source_fetchers_for(services, source_key),
        fred_source=fred_source,
        config=IngestionCoordinatorConfig(
            source_name=source_key.value,
            ingestion_log_store=services.ingestion_log_store,
            ingestion_cursor_store=runtime.ingestion_cursor_store,
            quality_checker=runtime.quality_checker,
            freeze_store=runtime.freeze_store,
            lineage_recorder=runtime.lineage_recorder,
            catalog_reader=runtime.catalog_reader,
            catalog_writer=runtime.catalog_writer,
        ),
    )


@contextmanager
def create_coordinator(
    services: CoordinatorServices,
    source_name: str | Source,
    *,
    runtime: CoordinatorRuntimeContext | None = None,
) -> Generator[IngestionCoordinatorLike]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        services: 协调器所需服务依赖.
        source_name: 数据源名称.
        runtime: 运行期可选 port 聚合.

    Yields:
        IngestionCoordinatorLike: 协调器实例

    """
    runtime_ctx = runtime or CoordinatorRuntimeContext()
    if isinstance(source_name, Source):
        source_key = source_name
    else:
        normalized_source_name = source_name.lower()
        if normalized_source_name == AUTO_SOURCE_NAME:
            coordinators = {
                source_key.value: _build_coordinator(
                    services,
                    source_key,
                    runtime=runtime_ctx,
                )
                for source_key in _auto_source_keys(services)
            }

            def date_range_lister(
                dataset: str,
                start_date: str,
                end_date: str,
            ) -> list[str]:
                return list_ingestion_dates(
                    dataset,
                    start_date,
                    end_date,
                    metadata_service=services.metadata_service,
                )

            yield AutoSourceIngestionCoordinator(
                coordinators,
                catalog_reader=runtime_ctx.catalog_reader,
                source_fallback_policy_reader=runtime_ctx.source_fallback_policy_reader,
                date_range_lister=date_range_lister,
                default_source=Source.TUSHARE.value,
            )
            return
        try:
            source_key = Source(normalized_source_name)
        except ValueError as e:
            supported = [*[s.value for s in Source], AUTO_SOURCE_NAME]
            raise AppProcessError(
                f"Unknown source: '{source_name}'. Supported sources: {supported}",
                field="source_name",
                value=source_name,
                supported=supported,
            ) from e

    coordinator = _build_coordinator(
        services,
        source_key,
        runtime=runtime_ctx,
    )

    yield coordinator


__all__ = [
    "CoordinatorRuntimeContext",
    "CoordinatorServices",
    "create_coordinator",
]
