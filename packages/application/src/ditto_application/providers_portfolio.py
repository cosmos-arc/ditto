"""App Query 层 DI Provider — 组合/交易查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_execution.contracts import FillDataPort, IntentDataPort, PositionDataPort

from ditto_application.queries.portfolio_actual import PortfolioActualQueryFacade
from ditto_application.queries.signal import SignalQueryFacade
from ditto_application.queries.trade import TradeQueryFacade

__all__ = ["AppPortfolioQueryProvider"]


class AppPortfolioQueryProvider(Provider):
    """App Query 层 DI Provider — 组合/交易查询服务注册。"""

    scope = Scope.APP

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
