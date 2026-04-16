"""App Query 层 DI Provider — 市场数据查询服务注册。"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
    DerivedQueryService,
    ResearchCatalogService,
)
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.research_artifact_service import ResearchArtifactService
from ditto_data.services.source_service import SourceService

from ditto_app.query.capital import CapitalQueryFacade
from ditto_app.query.commodity import CommodityQueryFacade
from ditto_app.query.derived import DerivedQueryFacade
from ditto_app.query.forward_return_service import ForwardReturnService
from ditto_app.query.fundamental import FundamentalQueryFacade
from ditto_app.query.fx import FXQueryFacade
from ditto_app.query.ingestion_status import IngestionStatusQueryFacade
from ditto_app.query.macro import MacroQueryFacade
from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.query.research import ResearchDatasetFacade
from ditto_app.query.source import SourceQueryFacade
from ditto_app.query.universe import UniverseQueryFacade

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
    ) -> MarketQueryFacade:
        """行情数据查询 facade — 隐藏内部查询类型."""
        return MarketQueryFacade(market_service=market_service)

    @provide
    def source_query_facade(
        self,
        source_service: SourceService,
        metadata_service: MetadataService,
    ) -> SourceQueryFacade:
        """数据源查询 facade — 隐藏 Dataset 枚举和服务接线."""
        return SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
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
    def metadata_query_facade(
        self,
        metadata_service: MetadataService,
    ) -> MetadataQueryFacade:
        """元数据查询 facade — 隐藏 SecurityQuery 和内部类型."""
        return MetadataQueryFacade(metadata_service=metadata_service)

    @provide
    def capital_query_facade(
        self,
        capital_service: CapitalService,
    ) -> CapitalQueryFacade:
        """资金查询 facade — 隐藏 CQRS 端口类型."""
        return CapitalQueryFacade(capital_service=capital_service)

    @provide
    def fundamental_query_facade(
        self,
        fundamental_service: FundamentalService,
    ) -> FundamentalQueryFacade:
        """基本面查询 facade — 隐藏 CQRS 端口类型."""
        return FundamentalQueryFacade(fundamental_service=fundamental_service)

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
        ingestion_log_service: IngestionLogService,
    ) -> IngestionStatusQueryFacade:
        """摄取状态查询 facade — 封装 IngestionLogService."""
        return IngestionStatusQueryFacade(ingestion_log_service=ingestion_log_service)
