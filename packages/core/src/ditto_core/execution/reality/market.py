"""
MarketSnapshot — 单个标的在某日的完整市场快照.

从 backtest/data_feed.py 迁移至 execution/reality/,
作为 Reality Models 的公共输入类型。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.identity import InstrumentId

__all__ = ["MarketSnapshot"]


@dataclass(frozen=True)
class MarketSnapshot:
    """
    单个标的在某日的完整市场快照.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        instrument_id: 标的 ID
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        prev_close: 前收盘价
        volume: 成交量
        amount: 成交额
        is_suspended: 是否停牌
        limit_up: 涨停价 (None = 无限制)
        limit_down: 跌停价 (None = 无限制)
        avg_volume_20d: 20 日均量 (None = 缺失)

    """

    trade_date: str
    instrument_id: InstrumentId
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: float
    amount: float
    is_suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    avg_volume_20d: float | None = None
