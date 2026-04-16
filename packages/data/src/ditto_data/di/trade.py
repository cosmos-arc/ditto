"""Trade DI Provider — 交易闭环 CRUD 服务注册."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from ditto_data.services.trade import TradeService
from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["TradeProvider"]


class TradeProvider(Provider):
    """交易闭环服务的 Data 层 DI 注册."""

    scope = Scope.APP

    @provide
    def trade_service(self, sqlite_client: SQLiteClient) -> TradeService:
        """交易意图/人工成交/实际持仓 CRUD 服务."""
        svc = TradeService(client=sqlite_client)
        svc.init_schema()
        return svc
