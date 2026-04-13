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

from ditto_app.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
)

__all__ = ["ManualTracker"]


def _deterministic_uuid(*parts: str) -> str:
    """基于输入部件生成确定性 UUID v5."""
    name = ":".join(parts)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


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
          3. 仅返回 quantity != 0 的持仓

        """
        # 1. PIT 截断: 仅保留 snapshot_date 及之前的成交 + 过滤策略 + 按标的分组
        filtered = [
            f
            for f in fills
            if f.strategy_id == strategy_id and f.trade_date <= snapshot_date
        ]
        if not filtered:
            return []

        sorted_fills = sorted(filtered, key=lambda f: f.instrument_id)
        grouped = groupby(sorted_fills, key=lambda f: f.instrument_id)

        snapshots: list[ActualPositionSnapshot] = []
        for instrument_id, group in grouped:
            group_list = sorted(group, key=lambda f: f.trade_date)
            snapshot = self._compute_single_instrument(
                fills=group_list,
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
        instrument_id: int,
        strategy_id: str,
        snapshot_date: str,
        market_price: float | None,
    ) -> ActualPositionSnapshot | None:
        """对单个标的聚合计算持仓快照."""
        quantity = 0
        avg_cost = 0.0
        total_fees = 0.0
        realized_pnl = 0.0
        unsettled_buy_quantity = 0  # 当天买入未交收的累计量

        for fill in fills:
            total_fees += fill.fee

            if fill.direction == "buy":
                old_qty = quantity
                new_qty = fill.quantity
                total_qty = old_qty + new_qty
                if total_qty > 0:
                    avg_cost = (
                        avg_cost * old_qty + fill.fill_price * new_qty
                    ) / total_qty
                quantity = total_qty

                # T+1: 买入当天冻结
                settlement = self.compute_settlement_date(fill.trade_date, cycle=1)
                if settlement > snapshot_date:
                    unsettled_buy_quantity += new_qty

            elif fill.direction == "sell":
                sell_qty = fill.quantity
                if sell_qty > quantity:
                    msg = (
                        f"oversold instrument_id={instrument_id}: "
                        f"trying to sell {sell_qty} but holding {quantity}"
                    )
                    raise ValueError(msg)
                # 已实现盈亏 = (卖出价 - 平均成本) * 卖出数量
                realized_pnl += (fill.fill_price - avg_cost) * sell_qty
                quantity -= sell_qty

        # 仅返回 quantity != 0 的持仓
        if quantity == 0:
            return None

        # available_quantity = quantity - 未交收的买入量
        available_quantity = max(0, quantity - unsettled_buy_quantity)

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
