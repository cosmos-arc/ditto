"""App Query 层 DI Provider — 组合/交易查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_execution.contracts import (
    AccountDataPort,
    FillDataPort,
    IntentDataPort,
    PositionDataPort,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.queries.account import AccountBaselineQuery
from ditto_application.queries.daily_decision import DailyDecisionQueryFacade
from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.trade import TradeQueryFacade

__all__ = ["AppPortfolioQueryProvider"]


class AppPortfolioQueryProvider(Provider):
    """App Query 层 DI Provider — 组合/交易查询服务注册。"""

    scope = Scope.APP

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
    ) -> DailyDecisionQueryFacade:
        """每日决策查询 facade — 聚合信号、持仓、偏差和 P&L."""
        return DailyDecisionQueryFacade(
            signal_facade=signal_facade,
            portfolio_facade=portfolio_facade,
            deviation_facade=deviation_facade,
            package_reader=artifact_service,
        )
