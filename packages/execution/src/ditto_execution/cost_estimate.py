"""费用/滑点预估 — 成交额与交易成本计算."""

from __future__ import annotations

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules, MarketSnapshot

from ditto_execution.orders.model import Order

__all__ = [
    "calc_cost",
    "calc_turnover",
    "get_estimated_price",
]


def get_estimated_price(
    market: dict[InstrumentId, MarketSnapshot],
    iid: InstrumentId,
) -> float:
    """获取预估价格。"""
    snap = market.get(iid)
    return snap.close if snap else 0.0


def calc_turnover(
    orders: list[Order],
    market: dict[InstrumentId, MarketSnapshot],
) -> float:
    """计算预估成交额。"""
    turnover = 0.0
    for o in orders:
        snap = market.get(o.instrument_id)
        price = snap.close if snap else 0.0
        turnover += abs(o.quantity) * price
    return turnover


def calc_cost(
    turnover: float,
    instrument_rules: dict[InstrumentId, InstrumentRules],
) -> float:
    """计算预估交易成本 (使用各标的最大费率)。"""
    if not instrument_rules or turnover == 0:
        return 0.0
    max_rate = max(
        r[2].commission_rate + r[2].stamp_duty_rate + r[2].transfer_fee_rate
        for r in instrument_rules.values()
    )
    return turnover * max_rate
