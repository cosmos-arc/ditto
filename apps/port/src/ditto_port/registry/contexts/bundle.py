"""上下文组合包定义."""

from dataclasses import dataclass

from ditto_datahub.services import IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.derived_migration_service import (
    LegacyDerivedCatalogMigrationService,
)
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from ditto_datahub.sources import ExchangeTransformers

from ditto_port.services.derived import (
    DerivedInvalidationOrchestrator,
    DerivedMaterializationOrchestrator,
    DerivedPublicationFacade,
    ResearchDatasetFacade,
)
from ditto_port.services.ingestion.backfill import BackfillManager
from ditto_port.services.ingestion.coordinator import IngestionCoordinator


@dataclass(frozen=True)
class IngestionBundle:
    """
    摄入上下文组合包.

    包含数据摄入所需的所有服务和协调器。
    解决 ARCH-003（组合逻辑分散）和 ARCH-004（重复容器）问题。
    """

    metadata_service: MetadataService
    market_service: MarketService
    fundamental_service: FundamentalService
    capital_service: CapitalService
    macro_service: MacroService
    source_service: SourceService
    ingestion_log_service: IngestionLogService
    exchange_transformers: ExchangeTransformers
    coordinator: IngestionCoordinator
    backfill_manager: BackfillManager


@dataclass(frozen=True)
class MaterializationBundle:
    """物化上下文组合包。"""

    materialization_service: DerivedMaterializationOrchestrator
    invalidation_service: DerivedInvalidationOrchestrator
    migration_service: LegacyDerivedCatalogMigrationService
    publication_facade: DerivedPublicationFacade
    research_dataset_facade: ResearchDatasetFacade
