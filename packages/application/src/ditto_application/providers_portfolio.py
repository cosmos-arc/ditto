"""App Query 层 DI Provider — 组合/交易查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_execution.paper.session import PaperSessionStorePort
from ditto_portfolio.account_ledger import AccountEventJournalPort
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

from ditto_application.commands.paper_session import PaperSessionCommandHandler
from ditto_application.etf_paper_execution import ETFPaperExecution
from ditto_application.etf_paper_handoff import ETFPaperHandoff
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_application.processes.execution.signal_package import SignalPackagePublisher
from ditto_application.processes.portfolio.etf_allocation import ETFAllocationCommand
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
from ditto_application.queries.etf_paper_execution_facts import (
    LiveETFPaperExecutionFacts,
)
from ditto_application.queries.etf_paper_handoff_facts import LiveETFPaperHandoffFacts
from ditto_application.queries.field_admission import FieldAdmissionQuery
from ditto_application.queries.history_comparison import GetHistoryComparisonQuery
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.model_history import GetModelHistoryQuery
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
from ditto_application.queries.portfolio_history import (
    GetManualHistoryQuery,
    GetPaperHistoryQuery,
)
from ditto_application.queries.portfolio_scenario import PreviewPortfolioScenarioQuery
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_application.queries.technical_analysis import TechnicalAnalysisSourcePort
from ditto_application.queries.technical_analysis_source import (
    ProviderPayloadTechnicalAnalysisSource,
)
from ditto_application.queries.trade import TradeQueryFacade

__all__ = ["AppPortfolioQueryProvider"]


class AppPortfolioQueryProvider(Provider):
    """App Query 层 DI Provider — 组合/交易查询服务注册。"""

    scope = Scope.APP

    @provide
    def etf_allocation_command(
        self, metadata: MetadataQueryFacade, artifacts: StrategyArtifactService
    ) -> ETFAllocationCommand:
        """Validate and save ETF research allocation revisions."""
        return ETFAllocationCommand(metadata, artifacts)

    @provide
    def etf_paper_handoff_facts(
        self,
        metadata: MetadataQueryFacade,
        admission: FieldAdmissionQuery,
        snapshots: ProviderSnapshotReader,
        ledger: AccountLedgerQuery,
    ) -> LiveETFPaperHandoffFacts:
        """Resolve current, promotion-admitted ETF and PAPER account facts."""
        return LiveETFPaperHandoffFacts(
            metadata=metadata,
            admission=admission,
            snapshots=snapshots,
            ledger=ledger,
        )

    @provide
    def etf_paper_handoff(
        self,
        allocations: ETFAllocationCommand,
        facts: LiveETFPaperHandoffFacts,
        packages: SignalPackagePublisher,
        sessions: PaperSessionCommandHandler,
    ) -> ETFPaperHandoff:
        """Bind fixed target approval, package publication and PAPER session."""
        return ETFPaperHandoff(
            allocations=allocations,
            facts=facts,
            packages=packages,
            sessions=sessions,
        )

    @provide
    def etf_paper_execution_facts(
        self,
        metadata: MetadataQueryFacade,
        admission: FieldAdmissionQuery,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        ledger: AccountLedgerQuery,
    ) -> LiveETFPaperExecutionFacts:
        """Provide the retained and admitted ETF Paper fact reader."""
        return LiveETFPaperExecutionFacts(
            metadata=metadata,
            admission=admission,
            snapshots=snapshots,
            payloads=payloads,
            bars=ProviderPayloadTechnicalAnalysisSource(
                snapshot_reader=snapshots,
                payload_reader=payloads,
            ),
            ledger=ledger,
        )

    @provide
    def etf_paper_execution(
        self,
        allocations: ETFAllocationCommand,
        packages: SignalPackagePublisher,
        sessions: PaperSessionStorePort,
        facts: LiveETFPaperExecutionFacts,
        operator: OperatePaperSession,
    ) -> ETFPaperExecution:
        """Provide the governed ETF Paper executor."""
        return ETFPaperExecution(
            allocations=allocations,
            packages=packages,
            sessions=sessions,
            facts=facts,
            operator=operator,
        )

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
    def manual_history_query(
        self,
        journal: AccountEventJournalPort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> GetManualHistoryQuery:
        """Replay one MANUAL ledger revision into flow-adjusted returns."""
        return GetManualHistoryQuery(
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        )

    @provide
    def paper_history_query(
        self,
        journal: AccountEventJournalPort,
        paper_store: PaperSessionStorePort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> GetPaperHistoryQuery:
        """Replay one session-bound PAPER ledger revision into returns."""
        return GetPaperHistoryQuery(
            journal=journal,
            session_store=paper_store,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        )

    @provide
    def model_history_query(
        self,
        artifact_reader: StrategyArtifactService,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> GetModelHistoryQuery:
        """Replay saved strategy targets into a cost-free return series."""
        return GetModelHistoryQuery(
            artifact_reader=artifact_reader,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        )

    @provide
    def history_comparison_query(
        self,
        manual_history: GetManualHistoryQuery,
        paper_history: GetPaperHistoryQuery,
        model_history: GetModelHistoryQuery,
        journal: AccountEventJournalPort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> GetHistoryComparisonQuery:
        """Compose the three leg replays into one common-window comparison."""
        return GetHistoryComparisonQuery(
            manual_query=manual_history,
            paper_query=paper_history,
            model_query=model_history,
            journal=journal,
            snapshot_reader=snapshot_reader,
            valuation_source=valuation_source,
        )

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
