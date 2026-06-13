"""App Query 层 DI Provider — 市场数据查询服务注册。"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_data.catalog import DataCatalogReader
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionReader,
    DatasetPromotionEvidenceReader,
)
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_features.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
)

from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.catalog import CatalogQueryFacade
from ditto_application.queries.commodity import CommodityQueryFacade
from ditto_application.queries.derived import DerivedQueryFacade
from ditto_application.queries.forward_return_service import ForwardReturnService
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.fx import FXQueryFacade
from ditto_application.queries.ingestion_status import IngestionStatusQueryFacade
from ditto_application.queries.macro import MacroQueryFacade
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.research import ResearchDatasetFacade
from ditto_application.queries.source import SourceDataPort, SourceQueryFacade
from ditto_application.queries.universe import UniverseQueryFacade

__all__ = ["AppMarketQueryProvider"]


class AppMarketQueryProvider(Provider):
    """App Query 层 DI Provider — 市场数据查询服务注册。"""

    scope = Scope.APP

    @provide
    def forward_return_service(
        self,
        market_service: MarketService,
    ) -> ForwardReturnService:
        """前向收益率计算服务."""
        return ForwardReturnService(market_service=market_service)

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
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> MarketQueryFacade:
        """行情数据查询 facade — 隐藏内部查询类型."""
        return MarketQueryFacade(
            market_service=market_service,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def source_query_facade(
        self,
        source_data: SourceDataPort,
        metadata_service: MetadataService,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> SourceQueryFacade:
        """数据源查询 facade — 通过 Protocol 获取 source 数据."""
        return SourceQueryFacade(
            source_data=source_data,
            metadata_service=metadata_service,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def research_dataset_facade(
        self,
        metadata_service: MetadataService,
        research_catalog_service: ResearchCatalogService,
        derived_catalog_service: DerivedCatalogService,
        research_artifact_service: ResearchArtifactService,
        settings: DataStoreSettings,
    ) -> ResearchDatasetFacade:
        """研究数据集快照构建 facade."""
        return ResearchDatasetFacade(
            metadata_service=metadata_service,
            research_catalog_service=research_catalog_service,
            artifact_reader=DerivedArtifactReader(
                catalog_service=derived_catalog_service,
                artifact_root=Path(settings.data_root),
            ),
            research_artifact_service=research_artifact_service,
        )

    @provide
    def catalog_query_facade(
        self,
        data_catalog_reader: DataCatalogReader,
        maturity_promotion_history_reader: DatasetMaturityPromotionHistoryReader,
        catalog_source_fallback_policy_reader: CatalogSourceFallbackPolicyReader,
    ) -> CatalogQueryFacade:
        """DataCatalog 查询 facade — 暴露 storage/schema/freshness 读模型."""
        return CatalogQueryFacade(
            data_catalog_reader=data_catalog_reader,
            maturity_promotion_history_reader=maturity_promotion_history_reader,
            source_fallback_policy_reader=catalog_source_fallback_policy_reader,
        )

    @provide
    def metadata_query_facade(
        self,
        metadata_service: MetadataService,
    ) -> MetadataQueryFacade:
        """元数据查询 facade — 隐藏 SecurityQuery 和内部类型."""
        return MetadataQueryFacade(metadata_service=metadata_service)

    @provide
    def capital_query_facade(
        self,
        capital_store: CapitalStore,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> CapitalQueryFacade:
        """资金查询 facade — 隐藏 CQRS 端口类型."""
        return CapitalQueryFacade(
            capital_store=capital_store,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def fundamental_query_facade(
        self,
        fundamental_store: FundamentalStore,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> FundamentalQueryFacade:
        """基本面查询 facade — 隐藏 CQRS 端口类型."""
        return FundamentalQueryFacade(
            fundamental_store=fundamental_store,
            maturity_promotion_reader=maturity_promotion_reader,
        )

    @provide
    def macro_query_facade(
        self,
        macro_service: MacroService,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
    ) -> MacroQueryFacade:
        """宏观查询 facade — 隐藏 MacroQuery 和枚举类型."""
        return MacroQueryFacade(
            macro_service=macro_service,
            maturity_promotion_reader=maturity_promotion_reader,
        )

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
        promotion_evidence_reader: DatasetPromotionEvidenceReader,
        maturity_promotion_reader: DatasetMaturityPromotionReader,
        maturity_promotion_history_reader: DatasetMaturityPromotionHistoryReader,
        catalog_query_facade: CatalogQueryFacade,
    ) -> IngestionStatusQueryFacade:
        """摄取状态查询 facade — 封装 log 与 catalog freshness 读模型."""
        return IngestionStatusQueryFacade(
            ingestion_log_store=ingestion_log_store,
            data_catalog_reader=data_catalog_reader,
            promotion_evidence_reader=promotion_evidence_reader,
            maturity_promotion_reader=maturity_promotion_reader,
            maturity_promotion_history_reader=maturity_promotion_history_reader,
            source_health_summary_query=catalog_query_facade,
        )
