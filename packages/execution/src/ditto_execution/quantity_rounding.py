"""100+1 数量取整 — 买入最小1手, 卖出拆分整手+零股."""

from __future__ import annotations

from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules

__all__ = [
    "get_lot_size",
    "round_buy_qty",
    "sell_quantities",
    "target_quantity",
]


def get_lot_size(
    instrument_rules: dict[InstrumentId, InstrumentRules],
    iid: InstrumentId,
    default_lot_size: int,
) -> int:
    """获取标的 lot_size，优先使用 InstrumentDefinition。"""
    if iid in instrument_rules:
        return instrument_rules[iid][0].lot_size
    return default_lot_size


def round_buy_qty(raw_qty: int, lot_size: int) -> int:
    """买入数量向下取整到整手；不足一手不强行交易。"""
    if raw_qty <= 0:
        return 0
    return (raw_qty // lot_size) * lot_size


def sell_quantities(raw_qty: int, lot_size: int) -> list[int]:
    """卖出数量拆分 — 整手 + 零股 (100+1 规则)。"""
    if raw_qty <= 0:
        return []
    round_lots = (raw_qty // lot_size) * lot_size
    odd_lots = raw_qty % lot_size
    result: list[int] = []
    if round_lots > 0:
        result.append(round_lots)
    if odd_lots > 0:
        result.append(odd_lots)
    return result


def target_quantity(
    weight: float,
    nav: float,
    lot_size: int,
    price: float = 0.0,
) -> int:
    """将目标权重转换为股数（向下取整到 lot_size 整数倍）。"""
    target_value = weight * nav
    if target_value < 1:
        return 0
    if price > 0:
        target_shares = target_value / price
        lots = int(target_shares / lot_size)
    else:
        lots = int(target_value / lot_size)
    return lots * lot_size
