"""费用/滑点预估 — 成交额与交易成本计算."""

from __future__ import annotations

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules, MarketSnapshot

from ditto_execution.orders.model import Order
from ditto_execution.reality.fee import AShareFeeModel

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
    orders: list[Order],
    market: dict[InstrumentId, MarketSnapshot],
    instrument_rules: dict[InstrumentId, InstrumentRules],
) -> float:
    """Estimate each planned order using its side, minimum and dated fee table."""
    total = 0.0
    for order in orders:
        price = get_estimated_price(market, order.instrument_id)
        rules = instrument_rules.get(order.instrument_id)
        # Legacy planners allow absent rules/quotes; ordinary launches validate
        # complete dated inputs before reaching this optional cost summary.
        if rules is None or price <= 0:
            continue
        total += AShareFeeModel().estimate(order, price, rules[2])
    return total
