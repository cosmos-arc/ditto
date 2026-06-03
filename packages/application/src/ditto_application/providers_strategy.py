"""App Query 层 DI Provider — 策略/回测查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.catalog import DataCatalogReader
from ditto_data.lineage import DataLineageReader
from ditto_execution.audit import ExecutionAuditService
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.storage.sqlite.services.backtest_artifact_reader import (
    BacktestArtifactReader,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_application.queries.backtest_trade import BacktestTradeQueryFacade
from ditto_application.queries.comparison import ComparisonQueryFacade
from ditto_application.queries.lineage import LineageQueryFacade
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_application.queries.run import RunReadModel
from ditto_application.queries.strategy import StrategyQueryFacade

__all__ = ["AppStrategyQueryProvider"]


class AppStrategyQueryProvider(Provider):
    """App Query 层 DI Provider — 策略/回测查询服务注册。"""

    scope = Scope.APP

    @provide
    def backtest_trade_query_facade(
        self,
        artifact_service: StrategyArtifactService,
    ) -> BacktestTradeQueryFacade:
        """回测成交查询 facade."""
        return BacktestTradeQueryFacade(artifact_service=artifact_service)

    @provide
    def backtest_artifact_reader(
        self,
    ) -> BacktestArtifactReader:
        """回测产物文件读取服务 — 封装 JSON/Parquet 文件 I/O."""
        return BacktestArtifactReader()

    @provide
    def run_read_model(
        self,
        run_service: StrategyRunLifecycleStore,
    ) -> RunReadModel:
        """回测运行读模型."""
        return RunReadModel(run_service=run_service)

    @provide
    def strategy_query_facade(
        self,
        catalog_service: StrategyCatalogReader,
    ) -> StrategyQueryFacade:
        """策略只读查询 facade — 封装 StrategyCatalogReader."""
        return StrategyQueryFacade(catalog_service=catalog_service)

    @provide
    def backtest_query_facade(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        artifact_reader: BacktestArtifactReader,
    ) -> BacktestQueryFacade:
        """回测统一查询门面."""
        return BacktestQueryFacade(
            trade_facade=trade_facade,
            run_model=run_model,
            audit_service=audit_service,
            artifact_service=artifact_service,
            artifact_reader=artifact_reader,
        )

    @provide
    def lineage_query_facade(
        self,
        run_service: StrategyRunLifecycleStore,
        data_lineage_reader: DataLineageReader,
        data_catalog_reader: DataCatalogReader,
    ) -> LineageQueryFacade:
        """运行血统查询 facade — 提供 lineage chain 查询."""
        return LineageQueryFacade(
            run_service=run_service,
            data_lineage_reader=data_lineage_reader,
            data_catalog_reader=data_catalog_reader,
        )

    @provide
    def comparison_query_facade(
        self,
        backtest_facade: BacktestQueryFacade,
        actual_facade: PortfolioActualQueryFacade,
        market_facade: MarketQueryFacade,
    ) -> ComparisonQueryFacade:
        """回测 vs 实际对比查询 facade."""
        return ComparisonQueryFacade(
            backtest_facade=backtest_facade,
            actual_facade=actual_facade,
            market_facade=market_facade,
        )
