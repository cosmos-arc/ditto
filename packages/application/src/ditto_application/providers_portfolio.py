"""App Query 层 DI Provider — 组合/交易查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_execution.paper.session import PaperSessionStorePort
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.daily_decision import DailyDecisionQueryFacade
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3ProjectionReader,
    DailyDecisionV3QueryFacade,
    NullDailyDecisionV3ProjectionReader,
)
from ditto_application.queries.decision_evidence import DecisionEvidenceQueryFacade
from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonSourcePort,
)
from ditto_application.queries.portfolio_comparison_evidence import (
    PortfolioComparisonEvidenceQueryFacade,
)
from ditto_application.queries.portfolio_comparison_source import (
    LivePortfolioComparisonSource,
)
from ditto_application.queries.portfolio_scenario import PreviewPortfolioScenarioQuery
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_application.queries.technical_analysis import TechnicalAnalysisSourcePort
from ditto_application.queries.trade import TradeQueryFacade

__all__ = ["AppPortfolioQueryProvider"]


class AppPortfolioQueryProvider(Provider):
    """App Query 层 DI Provider — 组合/交易查询服务注册。"""

    scope = Scope.APP

    @provide
    def portfolio_comparison_source(
        self,
        artifact_reader: StrategyArtifactService,
        account_query: AccountLedgerQuery,
        paper_store: PaperSessionStorePort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> PortfolioComparisonSourcePort:
        """Bind comparison facts to exact packages, ledgers, sessions, and PIT bars."""
        return LivePortfolioComparisonSource(
            artifact_reader=artifact_reader,
            account_query=account_query,
            paper_store=paper_store,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        )

    @provide
    def portfolio_comparison_query(
        self,
        source: PortfolioComparisonSourcePort,
    ) -> GetPortfolioComparisonQuery:
        """Expose the application-owned unified comparison read model."""
        return GetPortfolioComparisonQuery(source=source)

    @provide
    def portfolio_scenario_preview_query(
        self,
        comparison: GetPortfolioComparisonQuery,
    ) -> PreviewPortfolioScenarioQuery:
        """Expose deterministic read-only scenario previews."""
        return PreviewPortfolioScenarioQuery(comparison=comparison)

    @provide
    def portfolio_comparison_evidence_query(
        self,
        artifact_reader: StrategyArtifactService,
        comparison: GetPortfolioComparisonQuery,
        scenario: PreviewPortfolioScenarioQuery,
    ) -> PortfolioComparisonEvidenceQueryFacade:
        """Bind Agent evidence to exact package lineage and deterministic queries."""
        return PortfolioComparisonEvidenceQueryFacade(
            artifact_reader=artifact_reader,
            comparison=comparison,
            scenario=scenario,
        )

    @provide
    def daily_decision_v3_projection_reader(
        self,
    ) -> DailyDecisionV3ProjectionReader:
        """Fail closed until the apps composition root binds durable evidence."""
        return NullDailyDecisionV3ProjectionReader()

    @provide
    def account_baseline_query(
        self,
        account_port: AccountDataPort,
        position_port: PositionDataPort,
    ) -> AccountBaselineQuery:
        """账户基线按信号日查询服务。"""
        return AccountBaselineQuery(
            account_port=account_port,
            position_port=position_port,
        )

    @provide
    def trade_query_facade(
        self,
        intent_port: IntentDataPort,
    ) -> TradeQueryFacade:
        """交易意图查询 facade — 封装 IntentDataPort."""
        return TradeQueryFacade(intent_port=intent_port)

    @provide
    def portfolio_actual_query_facade(
        self,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
    ) -> PortfolioActualQueryFacade:
        """实际组合查询 facade — 封装 FillDataPort + PositionDataPort."""
        return PortfolioActualQueryFacade(
            fill_port=fill_port, position_port=position_port
        )

    @provide
    def signal_query_facade(
        self,
        intent_port: IntentDataPort,
    ) -> SignalQueryFacade:
        """信号查询 facade — 封装 IntentDataPort."""
        return SignalQueryFacade(intent_port=intent_port)

    @provide
    def signal_deviation_query_facade(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
    ) -> SignalDeviationQueryFacade:
        """信号-成交偏差查询 facade — 封装交易闭环 Ports."""
        return SignalDeviationQueryFacade(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
        )

    @provide
    def daily_decision_query_facade(
        self,
        signal_facade: SignalQueryFacade,
        portfolio_facade: PortfolioActualQueryFacade,
        deviation_facade: SignalDeviationQueryFacade,
        artifact_service: StrategyArtifactService,
        account_query: AccountBaselineQuery,
        strategy_query: StrategyQueryFacade,
        run_service: StrategyRunLifecycleStore,
    ) -> DailyDecisionQueryFacade:
        """每日决策查询 facade — 聚合信号、持仓、偏差和 P&L."""
        return DailyDecisionQueryFacade(
            signal_facade=signal_facade,
            portfolio_facade=portfolio_facade,
            deviation_facade=deviation_facade,
            package_reader=artifact_service,
            account_query=account_query,
            strategy_query=strategy_query,
            run_reader=run_service,
        )

    @provide
    def daily_decision_v3_query_facade(
        self,
        v2_facade: DailyDecisionQueryFacade,
        projection_reader: DailyDecisionV3ProjectionReader,
    ) -> DailyDecisionV3QueryFacade:
        """Daily Decision V3 facade with apps-provided R4 persistence reader."""
        return DailyDecisionV3QueryFacade(
            v2_facade=v2_facade,
            projection_reader=projection_reader,
        )

    @provide
    def decision_evidence_query_facade(
        self,
        daily_decision_v3: DailyDecisionV3QueryFacade,
    ) -> DecisionEvidenceQueryFacade:
        """Wrap DailyDecision V3 in an exact, PIT-bound read contract."""
        return DecisionEvidenceQueryFacade(daily_decision_v3=daily_decision_v3)
