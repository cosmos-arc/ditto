"""App Query 层 DI Provider — 组合/交易查询服务注册。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_data.services.trade import TradeService

from ditto_app.query.portfolio_actual import PortfolioActualQueryFacade
from ditto_app.query.signal import SignalQueryFacade
from ditto_app.query.trade import TradeQueryFacade

__all__ = ["AppPortfolioQueryProvider"]


class AppPortfolioQueryProvider(Provider):
    """App Query 层 DI Provider — 组合/交易查询服务注册。"""

    scope = Scope.APP

    @provide
    def trade_query_facade(
        self,
        trade_service: TradeService,
    ) -> TradeQueryFacade:
        """交易意图查询 facade — 封装 TradeService."""
        return TradeQueryFacade(trade_service=trade_service)

    @provide
    def portfolio_actual_query_facade(
        self,
        trade_service: TradeService,
    ) -> PortfolioActualQueryFacade:
        """实际组合查询 facade — 封装 TradeService 的持仓/成交/P&L 查询."""
        return PortfolioActualQueryFacade(trade_service=trade_service)

    @provide
    def signal_query_facade(
        self,
        trade_service: TradeService,
    ) -> SignalQueryFacade:
        """信号查询 facade — 封装 TradeService 的意图查询."""
        return SignalQueryFacade(trade_service=trade_service)
