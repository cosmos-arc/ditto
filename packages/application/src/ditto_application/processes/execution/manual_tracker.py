"""
ManualTracker — 从 Fill 聚合 → 实际持仓/P&L (含 T+1 交收).

纯计算类，不执行 I/O 操作。调用方负责提供 fills 数据。

职责:
  - 按标的分组、按时间排序聚合所有成交
  - 加权平均成本法计算持仓成本
  - 卖出时计算已实现盈亏
  - T+1 交收规则计算可卖数量
  - 可选市价计算未实现盈亏
"""

from __future__ import annotations

import uuid
from itertools import groupby

from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
)

__all__ = ["ManualTracker"]


def _deterministic_uuid(*parts: str) -> str:
    """基于输入部件生成确定性 UUID v5."""
    name = ":".join(parts)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def _apply_buy_fill(
    quantity: int,
    avg_cost: float,
    fill: ManualExecutionFill,
) -> tuple[int, float]:
    """
    处理买入成交: 加权平均成本计算 + T+1 交收检查.

    Returns:
        (new_quantity, new_avg_cost)

    """
    old_qty = quantity
    new_qty = fill.quantity
    total_qty = old_qty + new_qty
    if total_qty > 0:
        avg_cost = (avg_cost * old_qty + fill.fill_price * new_qty) / total_qty

    return total_qty, avg_cost


def _release_settled_buys(
    pending: list[tuple[str, str, int]],
    *,
    as_of_date: str,
) -> tuple[int, list[tuple[str, str, int]]]:
    """Release buys settled before a later processing date, never on trade day."""
    released = 0
    remaining: list[tuple[str, str, int]] = []
    for settlement_date, trade_date, quantity in pending:
        if settlement_date <= as_of_date and trade_date < as_of_date:
            released += quantity
        else:
            remaining.append((settlement_date, trade_date, quantity))
    return released, remaining


def _apply_sell_fill(
    quantity: int,
    available_quantity: int,
    avg_cost: float,
    fill: ManualExecutionFill,
    instrument_id: int,
) -> tuple[int, int, float]:
    """
    处理卖出成交: 超卖验证 + 已实现盈亏计算.

    Returns:
        (remaining_quantity, remaining_available_quantity, realized_pnl_increment)

    Raises:
        AppProcessError: 卖出数量超过当前持仓.

    """
    sell_qty = fill.quantity
    if sell_qty > quantity:
        msg = (
            f"oversold instrument_id={instrument_id}: "
            f"trying to sell {sell_qty} but holding {quantity}"
        )
        raise AppProcessError(msg)
    if sell_qty > available_quantity:
        msg = (
            f"unavailable instrument_id={instrument_id}: "
            f"trying to sell {sell_qty} but available {available_quantity}"
        )
        raise AppProcessError(msg)

    realized_pnl_increment = (fill.fill_price - avg_cost) * sell_qty
    return (
        quantity - sell_qty,
        available_quantity - sell_qty,
        realized_pnl_increment,
    )


class ManualTracker:
    """
    从 Fill 聚合 → 实际持仓/P&L (含 T+1 交收).

    Attributes:
        _calendar: 排序后的交易日历集合，用于 T+N 交收日期计算。

    """

    def __init__(self, trading_calendar: tuple[str, ...] = ()) -> None:
        self._calendar = trading_calendar

    # -------------------------------------------------------------------
    # 公开 API
    # -------------------------------------------------------------------

    def compute_positions(
        self,
        fills: list[ManualExecutionFill],
        strategy_id: str,
        snapshot_date: str,
        market_prices: dict[int, float] | None = None,
        opening_positions: tuple[ActualPositionSnapshot, ...] = (),
    ) -> list[ActualPositionSnapshot]:
        """
        从所有 Fill 聚合 → ActualPositionSnapshot 列表.

        逻辑:
          1. 过滤 strategy_id + 按 instrument_id 分组
          2. 对每个 instrument_id:
             a. 按 trade_date 排序 fills
             b. 累计: quantity, avg_cost (加权平均), total_fees
             c. 卖出时计算已实现盈亏
             d. 计算 T+1 available_quantity
             e. 可选市价计算未实现盈亏
          3. 全平后仅在仍有 realized P&L/fee 证据时保留零数量快照

        """
        # 1. PIT 截断: 仅保留 snapshot_date 及之前的成交 + 过滤策略 + 按标的分组
        filtered = [
            f
            for f in fills
            if f.strategy_id == strategy_id and f.trade_date <= snapshot_date
        ]
        opening_by_instrument = _opening_positions_by_instrument(
            opening_positions,
            strategy_id=strategy_id,
            snapshot_date=snapshot_date,
        )
        if not filtered and not opening_by_instrument:
            return []

        sorted_fills = sorted(filtered, key=lambda f: f.instrument_id)
        fills_by_instrument = {
            instrument_id: list(group)
            for instrument_id, group in groupby(
                sorted_fills,
                key=lambda fill: fill.instrument_id,
            )
        }

        snapshots: list[ActualPositionSnapshot] = []
        instrument_ids = sorted(set(fills_by_instrument) | set(opening_by_instrument))
        for instrument_id in instrument_ids:
            group_list = sorted(
                fills_by_instrument.get(instrument_id, ()),
                key=lambda fill: fill.trade_date,
            )
            snapshot = self._compute_single_instrument(
                fills=group_list,
                opening=opening_by_instrument.get(instrument_id),
                instrument_id=instrument_id,
                strategy_id=strategy_id,
                snapshot_date=snapshot_date,
                market_price=(
                    market_prices.get(instrument_id) if market_prices else None
                ),
            )
            if snapshot is not None:
                snapshots.append(snapshot)

        return snapshots

    def compute_settlement_date(self, trade_date: str, cycle: int = 1) -> str:
        """计算 T+N 交收日期（跳过非交易日）."""
        if not self._calendar:
            return trade_date

        sorted_calendar = sorted(self._calendar)
        try:
            idx = sorted_calendar.index(trade_date)
        except ValueError:
            return trade_date

        target_idx = idx + cycle
        if target_idx < len(sorted_calendar):
            return sorted_calendar[target_idx]
        # 超出日历范围时返回最后一个交易日
        return sorted_calendar[-1]

    # -------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------

    def _compute_single_instrument(
        self,
        fills: list[ManualExecutionFill],
        opening: ActualPositionSnapshot | None,
        instrument_id: int,
        strategy_id: str,
        snapshot_date: str,
        market_price: float | None,
    ) -> ActualPositionSnapshot | None:
        """对单个标的聚合计算持仓快照."""
        quantity = opening.quantity if opening is not None else 0
        available_quantity = opening.available_quantity if opening is not None else 0
        avg_cost = opening.average_cost if opening is not None else 0.0
        total_fees = opening.total_fees if opening is not None else 0.0
        realized_pnl = opening.realized_pnl if opening is not None else 0.0
        pending_buys: list[tuple[str, str, int]] = []

        for fill in fills:
            released, pending_buys = _release_settled_buys(
                pending_buys,
                as_of_date=fill.trade_date,
            )
            available_quantity += released
            total_fees += fill.fee

            if fill.direction == "buy":
                quantity, avg_cost = _apply_buy_fill(
                    quantity,
                    avg_cost,
                    fill,
                )
                pending_buys.append(
                    (
                        fill.settlement_date
                        or self.compute_settlement_date(fill.trade_date, cycle=1),
                        fill.trade_date,
                        fill.quantity,
                    )
                )

            elif fill.direction == "sell":
                quantity, available_quantity, pnl_inc = _apply_sell_fill(
                    quantity,
                    available_quantity,
                    avg_cost,
                    fill,
                    instrument_id,
                )
                realized_pnl += pnl_inc

        released, _ = _release_settled_buys(
            pending_buys,
            as_of_date=snapshot_date,
        )
        available_quantity += released

        if quantity == 0 and realized_pnl == 0.0 and total_fees == 0.0:
            return None

        # 未实现盈亏 & 市值
        if market_price is not None:
            unrealized_pnl = (market_price - avg_cost) * quantity
            market_value = market_price * quantity
        else:
            unrealized_pnl = 0.0
            market_value = 0.0

        # 生成确定性 snapshot_id
        snapshot_id = _deterministic_uuid(
            strategy_id,
            snapshot_date,
            str(instrument_id),
        )

        return ActualPositionSnapshot(
            snapshot_id=snapshot_id,
            strategy_id=strategy_id,
            snapshot_date=snapshot_date,
            instrument_id=instrument_id,
            quantity=quantity,
            available_quantity=available_quantity,
            average_cost=avg_cost,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            total_fees=total_fees,
        )


def _opening_positions_by_instrument(
    positions: tuple[ActualPositionSnapshot, ...],
    *,
    strategy_id: str,
    snapshot_date: str,
) -> dict[int, ActualPositionSnapshot]:
    """Validate and index the exact opening position set for one replay."""
    indexed: dict[int, ActualPositionSnapshot] = {}
    for position in positions:
        if (
            position.strategy_id != strategy_id
            or position.snapshot_date > snapshot_date
        ):
            continue
        if position.instrument_id in indexed:
            raise AppProcessError(
                f"duplicate opening position: {position.instrument_id}"
            )
        if not 0 <= position.available_quantity <= position.quantity:
            raise AppProcessError(
                f"invalid opening availability: {position.instrument_id}"
            )
        indexed[position.instrument_id] = position
    return indexed
