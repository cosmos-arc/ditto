"""
TradeBuilder — FIFO trade matching (v3 §8.2).

Consumes FillEvent, matches entry/exit pairs by FIFO protocol,
produces TradeRecord (open or closed).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from ditto_core.accounting.account import AccountView
from ditto_core.accounting.order_book import OrderDirection
from ditto_core.execution.fills import FillEvent

__all__ = [
    "FifoTradeBuilder",
    "TradeBuilder",
    "TradeMatchingMethod",
    "TradeRecord",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TradeMatchingMethod(StrEnum):
    """成交匹配方式。"""

    FIFO = "fifo"
    FLAT_TO_FLAT = "flat_to_flat"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeRecord:
    """一笔完整交易 — 从 entry fill 到 exit fill。"""

    trade_id: str
    instrument_id: str
    direction: OrderDirection
    entry_date: str
    exit_date: str | None
    entry_price: float
    exit_price: float | None
    quantity: int
    gross_pnl: float | None
    fees: float
    net_pnl: float | None
    holding_days: int | None
    return_pct: float | None
    entry_order_ids: tuple[str, ...]
    exit_order_ids: tuple[str, ...]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class TradeBuilder(Protocol):
    """成交构建协议 — 将 fills 转换为 trades。"""

    def on_fill(self, fill: FillEvent, account_view: AccountView) -> None:
        """处理成交事件，更新开仓/平仓记录。"""
        ...

    def get_open_trades(self) -> tuple[TradeRecord, ...]:
        """获取当前未平仓交易。"""
        ...

    def get_closed_trades(self) -> tuple[TradeRecord, ...]:
        """获取已平仓交易。"""
        ...

    def flush(self) -> tuple[TradeRecord, ...]:
        """刷新所有未平仓交易为已平仓。"""
        ...


# ---------------------------------------------------------------------------
# Internal mutable container
# ---------------------------------------------------------------------------


@dataclass
class _OpenEntry:
    """FIFO 匹配的可变跟踪条目。"""

    trade_id: str
    instrument_id: str
    direction: OrderDirection
    entry_date: date
    entry_price: float
    entry_fee: float
    original_quantity: int
    remaining_quantity: int
    entry_order_id: str


# ---------------------------------------------------------------------------
# FIFO implementation
# ---------------------------------------------------------------------------


class FifoTradeBuilder:
    """FIFO 成交匹配 — 卖出时平仓最早的开仓买入。"""

    def __init__(self) -> None:
        # instrument_id → FIFO queue of open entries
        self._open: dict[str, deque[_OpenEntry]] = {}
        self._closed: list[TradeRecord] = []
        self._counter = 0

    # -- public API ---------------------------------------------------------

    def on_fill(self, fill: FillEvent, account_view: AccountView) -> None:
        """处理成交事件，更新开仓/平仓记录。"""
        iid = fill.instrument_id
        fill_date = fill.event_time.date()

        if fill.direction == OrderDirection.BUY:
            self._open.setdefault(iid, deque()).append(
                _OpenEntry(
                    trade_id=self._next_id(),
                    instrument_id=iid,
                    direction=OrderDirection.BUY,
                    entry_date=fill_date,
                    entry_price=fill.fill_price,
                    entry_fee=fill.fee,
                    original_quantity=fill.filled_quantity,
                    remaining_quantity=fill.filled_quantity,
                    entry_order_id=fill.order_id,
                ),
            )

        elif fill.direction == OrderDirection.SELL:
            self._match_sell(iid, fill_date, fill)

    def get_open_trades(self) -> tuple[TradeRecord, ...]:
        """获取当前未平仓交易。"""
        records: list[TradeRecord] = []
        for queue in self._open.values():
            for e in queue:
                records.append(
                    TradeRecord(
                        trade_id=e.trade_id,
                        instrument_id=e.instrument_id,
                        direction=e.direction,
                        entry_date=e.entry_date.isoformat(),
                        exit_date=None,
                        entry_price=e.entry_price,
                        exit_price=None,
                        quantity=e.remaining_quantity,
                        gross_pnl=None,
                        fees=0.0,
                        net_pnl=None,
                        holding_days=None,
                        return_pct=None,
                        entry_order_ids=(e.entry_order_id,),
                        exit_order_ids=(),
                    ),
                )
        return tuple(records)

    def get_closed_trades(self) -> tuple[TradeRecord, ...]:
        """获取已平仓交易。"""
        return tuple(self._closed)

    def flush(self) -> tuple[TradeRecord, ...]:
        """刷新所有未平仓交易为已平仓。"""
        open_records = self.get_open_trades()
        self._open.clear()
        return open_records

    # -- internals ----------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"trade-{self._counter}"

    def _match_sell(
        self,
        iid: str,
        fill_date: date,
        fill: FillEvent,
    ) -> None:
        queue = self._open.get(iid)
        if not queue:
            return

        remaining = fill.filled_quantity
        while remaining > 0 and queue:
            entry = queue[0]
            match_qty = min(remaining, entry.remaining_quantity)

            # Proportional fee allocation
            buy_fee_share = entry.entry_fee * (match_qty / entry.original_quantity)
            sell_fee_share = fill.fee * (match_qty / fill.filled_quantity)
            total_fee = buy_fee_share + sell_fee_share

            entry.remaining_quantity -= match_qty
            remaining -= match_qty

            holding = (fill_date - entry.entry_date).days
            pnl = (fill.fill_price - entry.entry_price) * match_qty
            self._closed.append(
                TradeRecord(
                    trade_id=self._next_id(),
                    instrument_id=entry.instrument_id,
                    direction=entry.direction,
                    entry_date=entry.entry_date.isoformat(),
                    exit_date=fill_date.isoformat(),
                    entry_price=entry.entry_price,
                    exit_price=fill.fill_price,
                    quantity=match_qty,
                    gross_pnl=pnl,
                    fees=total_fee,
                    net_pnl=pnl - total_fee,
                    holding_days=holding,
                    return_pct=(
                        (pnl / (entry.entry_price * match_qty)) * 100
                        if entry.entry_price > 0
                        else 0.0
                    ),
                    entry_order_ids=(entry.entry_order_id,),
                    exit_order_ids=(fill.order_id,),
                ),
            )

            if entry.remaining_quantity == 0:
                queue.popleft()
