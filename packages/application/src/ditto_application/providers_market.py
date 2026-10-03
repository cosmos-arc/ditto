"""App Query 层 DI Provider — 市场数据查询服务注册。"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_data.catalog import DataCatalogReader
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_features.market_context.service import MarketRegimeService
from ditto_features.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
)
from ditto_features.technical_analysis.service import TechnicalAnalysisService

from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.catalog import CatalogQueryFacade
from ditto_application.queries.commodity import CommodityQueryFacade
from ditto_application.queries.derived import DerivedQueryFacade
from ditto_application.queries.evaluation import FactorEvaluationFacade
from ditto_application.queries.forward_return_service import ForwardReturnService
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.fx import FXQueryFacade
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade
from ditto_application.queries.macro import MacroQueryFacade
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.market_chart import MarketChartQueryFacade
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextQueryPort,
    MarketContextQueryService,
    MarketContextSourcePort,
)
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_application.queries.market_context_source import (
    ProviderPayloadMarketContextSource,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.research import ResearchDatasetQuery
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_application.queries.source import SourceDataPort, SourceQueryFacade
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisQueryPort,
    TechnicalAnalysisQueryService,
    TechnicalAnalysisSourcePort,
)
from ditto_application.queries.technical_analysis_evidence import (
    InstrumentTechnicalEvidenceQueryFacade,
)
from ditto_application.queries.technical_analysis_source import (
    ProviderPayloadTechnicalAnalysisSource,
)
from ditto_application.queries.universe import UniverseQueryFacade

__all__ = ["AppMarketQueryProvider"]


class AppMarketQueryProvider(Provider):
    """App Query 层 DI Provider — 市场数据查询服务注册。"""

    scope = Scope.APP

    @provide
    def market_chart_query(
        self,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
        metadata: MetadataQueryFacade,
        market: MarketQueryFacade,
    ) -> MarketChartQueryFacade:
        """Wire exact retained market and calendar evidence for charts."""
        return MarketChartQueryFacade(snapshot_reader, payload_reader, metadata, market)

    @provide
    def technical_analysis_source(
        self,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> TechnicalAnalysisSourcePort:
        """Load exact technical bars from retained provider payloads."""
        return ProviderPayloadTechnicalAnalysisSource(
            snapshot_reader=snapshot_reader,
            payload_reader=payload_reader,
        )

    @provide
    def technical_analysis_query(
        self,
        source: TechnicalAnalysisSourcePort,
    ) -> TechnicalAnalysisQueryPort:
        """Build the deterministic technical-analysis query service."""
        return TechnicalAnalysisQueryService(source, TechnicalAnalysisService())

    @provide
    def technical_analysis_facade(
        self,
        snapshot_reader: ProviderSnapshotReader,
        query: TechnicalAnalysisQueryPort,
    ) -> TechnicalAnalysisFacade:
        """Resolve exact source identities before technical evaluation."""
        return TechnicalAnalysisFacade(snapshot_reader=snapshot_reader, query=query)

    @provide
    def instrument_technical_evidence_query_facade(
        self,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        technical_analysis: TechnicalAnalysisFacade,
    ) -> InstrumentTechnicalEvidenceQueryFacade:
        """Bind technical briefs to completed observed stock snapshots."""
        return InstrumentTechnicalEvidenceQueryFacade(
            snapshots=snapshots,
            lifecycle=lifecycle,
            technical_analysis=technical_analysis,
        )

    @provide
    def market_context_source(
        self,
        snapshot_reader: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> MarketContextSourcePort:
        """Load exact PIT facts from immutable provider payload artifacts."""
        return ProviderPayloadMarketContextSource(
            snapshot_reader=snapshot_reader,
            payload_reader=payload_reader,
        )

    @provide
    def market_context_query(
        self,
        source: MarketContextSourcePort,
    ) -> MarketContextQueryPort:
        """Build the shared deterministic market-context aggregate query."""
        return MarketContextQueryService(source, MarketRegimeService())

    @provide
    def market_context_facade(
        self,
        snapshot_reader: ProviderSnapshotReader,
        query: MarketContextQueryPort,
    ) -> MarketContextFacade:
        """Resolve exact provider snapshots before market-context evaluation."""
        return MarketContextFacade(snapshot_reader=snapshot_reader, query=query)

    @provide
    def market_context_evidence_query_facade(
        self,
        snapshots: ProviderSnapshotReader,
        lifecycle: PartitionLifecycleReader,
        market_context: MarketContextFacade,
    ) -> MarketContextEvidenceQueryFacade:
        """Bind Agent briefs to completed observed research-daily snapshots."""
        return MarketContextEvidenceQueryFacade(
            snapshots=snapshots,
            lifecycle=lifecycle,
            market_context=market_context,
        )

    @provide
    def forward_return_service(
        self,
        market_service: MarketService,
    ) -> ForwardReturnService:
        """前向收益率计算服务."""
        return ForwardReturnService(market_service=market_service)

    @provide
    def factor_evaluation_facade(
        self,
        derived_catalog_service: DerivedCatalogService,
        forward_return_service: ForwardReturnService,
        settings: DataStoreSettings,
    ) -> FactorEvaluationFacade:
        """因子 IC 评估 facade — 物化 artifact 读取 + 前向收益 + 评估编排."""
        return FactorEvaluationFacade(
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            forward_return_service=forward_return_service,
        )

    @provide
    def derived_query_facade(
        self,
        derived_query_service: DerivedQueryService,
    ) -> DerivedQueryFacade:
        """衍生数据查询用例 facade."""
        return DerivedQueryFacade(
            service=derived_query_service,
        )

    @provide
    def market_query_facade(
        self,
        market_service: MarketService,
        capital_store: CapitalStore,
    ) -> MarketQueryFacade:
        """行情数据查询 facade — 隐藏内部查询类型."""
        return MarketQueryFacade(
            market_service=market_service,
            capital_store=capital_store,
        )

    @provide
    def source_query_facade(
        self,
        source_data: SourceDataPort,
        metadata_service: MetadataService,
    ) -> SourceQueryFacade:
        """数据源查询 facade — 通过 Protocol 获取 source 数据."""
        return SourceQueryFacade(
            source_data=source_data,
            metadata_service=metadata_service,
        )

    @provide
    def research_dataset_query(
        self,
        research_catalog_service: ResearchCatalogService,
        research_artifact_service: ResearchArtifactService,
    ) -> ResearchDatasetQuery:
        """Read completed research snapshots."""
        return ResearchDatasetQuery(
            research_catalog_service=research_catalog_service,
            research_artifact_service=research_artifact_service,
        )

    @provide
    def catalog_query_facade(
        self,
        data_catalog_reader: DataCatalogReader,
    ) -> CatalogQueryFacade:
        """DataCatalog 查询 facade — 暴露 storage/schema/freshness 读模型."""
        return CatalogQueryFacade(data_catalog_reader=data_catalog_reader)

    @provide
    def metadata_query_facade(
        self,
        metadata_service: MetadataService,
        readiness: SnapshotReadinessQuery,
        snapshots: ProviderSnapshotReader,
        payload_reader: ProviderPayloadReader,
    ) -> MetadataQueryFacade:
        """元数据查询 facade — 隐藏 SecurityQuery 和内部类型."""
        return MetadataQueryFacade(
            metadata_service=metadata_service,
            readiness=readiness,
            snapshots=snapshots,
            payloads=payload_reader,
        )

    @provide
    def capital_query_facade(
        self,
        capital_store: CapitalStore,
    ) -> CapitalQueryFacade:
        """资金查询 facade — 隐藏 CQRS 端口类型."""
        return CapitalQueryFacade(capital_store=capital_store)

    @provide
    def fundamental_query_facade(
        self,
        fundamental_store: FundamentalStore,
    ) -> FundamentalQueryFacade:
        """基本面查询 facade — 隐藏 CQRS 端口类型."""
        return FundamentalQueryFacade(fundamental_store=fundamental_store)

    @provide
    def macro_query_facade(
        self,
        macro_service: MacroService,
    ) -> MacroQueryFacade:
        """宏观查询 facade — 隐藏 MacroQuery 和枚举类型."""
        return MacroQueryFacade(macro_service=macro_service)

    @provide
    def fx_query_facade(
        self,
        market_service: MarketService,
    ) -> FXQueryFacade:
        """外汇查询 facade — 隐藏 FX 代码映射和资产类别."""
        return FXQueryFacade(market_service=market_service)

    @provide
    def commodity_query_facade(
        self,
        market_service: MarketService,
    ) -> CommodityQueryFacade:
        """商品查询 facade — 隐藏 Commodity/VIX 映射和资产类别."""
        return CommodityQueryFacade(market_service=market_service)

    @provide
    def universe_query_facade(
        self,
        metadata_service: MetadataService,
    ) -> UniverseQueryFacade:
        """Universe 只读查询 facade — 封装 MetadataService universe 方法."""
        return UniverseQueryFacade(metadata_service=metadata_service)

    @provide
    def ingestion_status_query_facade(
        self,
        ingestion_log_store: IngestionLogStore,
        data_catalog_reader: DataCatalogReader,
    ) -> IngestionStatusQueryFacade:
        """摄取状态查询 facade — 封装 log 与 catalog freshness 读模型."""
        return IngestionStatusQueryFacade(
            ingestion_log_store=ingestion_log_store,
            data_catalog_reader=data_catalog_reader,
        )
