"""trade — 交易意图/人工成交/实际持仓 CRUD 服务包."""

from ditto_execution.storage.sqlite.trade.service import TradeService

__all__ = [
    "TradeService",
]
