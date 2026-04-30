"""上下文组合包定义."""

from dataclasses import dataclass

from ditto_app.process.execution.strategy_run_process import StrategyFacade
from ditto_app.process.execution.strategy_types import RunLifecycleService
from ditto_app.process.ingestion.backfill_manager import BackfillManager
from ditto_app.process.ingestion.coordinator import IngestionCoordinator
from ditto_app.process.ingestion.retry_manager import RetryManager
from ditto_app.process.materialization.cascade_orchestrator import (
    InvalidationCascadeOrchestrator,
)
from ditto_app.process.materialization.orchestrator import (
    DerivedMaterializationOrchestrator,
)
from ditto_app.process.materialization.publication_facade import (
    DerivedPublicationFacade,
)
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.query.research import ResearchDatasetFacade
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_data.services.strategy.strategy_run_service import StrategyRunWriterProtocol
from ditto_data.sources.exchange_transformers import ExchangeTransformers


@dataclass(frozen=True)
class IngestionBundle:
    """
    摄取上下文组合包.

    包含数据摄入所需的所有服务和协调器。
    解决 ARCH-003（组合逻辑分散）和 ARCH-004（重复容器）问题。
    """

    coordinator: IngestionCoordinator
    backfill_manager: BackfillManager
    retry_manager: RetryManager
    metadata_facade: MetadataQueryFacade
    exchange_transformers: ExchangeTransformers


@dataclass(frozen=True)
class MaterializationBundle:
    """物化上下文组合包。"""

    materialization_service: DerivedMaterializationOrchestrator
    invalidation_service: InvalidationCascadeOrchestrator
    publication_facade: DerivedPublicationFacade
    research_dataset_facade: ResearchDatasetFacade


@dataclass(frozen=True)
class StrategyBundle:
    """策略上下文组合包。"""

    strategy_facade: StrategyFacade
    catalog_service: StrategyCatalogService | None = None
    run_service: RunLifecycleService | None = None
    run_writer: StrategyRunWriterProtocol | None = None
