"""Backtest engine result model."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_execution.orders.model import Order
from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_backtest.manifest import RunManifest

__all__ = ["EngineResult", "EngineResultBuilder"]


@dataclass(frozen=True)
class EngineResult:
    """
    引擎运行结果 -- 不可变.

    产出后不可修改；运行过程中的可变累积由 EngineResultBuilder 负责。

    Attributes:
        run_id: 运行唯一 ID
        period: (start_date, end_date)
        final_nav: 最终净值
        total_trades: 总成交笔数
        orders: 所有提交的订单（tuple，不可变）
        fills: 所有成交事件（tuple，不可变）
        account_view: 最终账户快照
        manifest: 运行清单 (None = 未启用 RuleRefCollector)
        skipped_dates: Step 失败被跳过的日期
        cancelled: 是否被协作式取消

    """

    run_id: str
    period: tuple[str, str]
    final_nav: float = 0.0
    total_trades: int = 0
    orders: tuple[Order, ...] = ()
    fills: tuple[FillEvent, ...] = ()
    account_view: AccountView | None = None
    manifest: RunManifest | None = None
    skipped_dates: tuple[str, ...] = ()
    cancelled: bool = False


@dataclass
class EngineResultBuilder:
    """
    EngineResult 可变累积器 -- 运行过程中逐步收集 orders/fills/skipped.

    通过 build() 方法产出不可变的 EngineResult。
    """

    orders: list[Order] = field(default_factory=list)
    fills: list[FillEvent] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add_order(self, order: Order) -> None:
        """追加单个订单。"""
        self.orders.append(order)

    def add_fill(self, fill: FillEvent) -> None:
        """追加单个成交。"""
        self.fills.append(fill)

    def add_skipped(self, date: str) -> None:
        """追加一个跳过日期。"""
        self.skipped.append(date)

    def extend_orders(self, orders: list[Order]) -> None:
        """批量追加订单。"""
        self.orders.extend(orders)

    def extend_fills(self, fills: list[FillEvent]) -> None:
        """批量追加成交。"""
        self.fills.extend(fills)

    def build(
        self,
        *,
        run_id: str,
        period: tuple[str, str],
        final_nav: float,
        account_view: AccountView | None = None,
        manifest: RunManifest | None = None,
        cancelled: bool = False,
    ) -> EngineResult:
        """将累积状态转换为不可变的 EngineResult。"""
        return EngineResult(
            run_id=run_id,
            period=period,
            final_nav=final_nav,
            total_trades=len(self.fills),
            orders=tuple(self.orders),
            fills=tuple(self.fills),
            account_view=account_view,
            manifest=manifest,
            skipped_dates=tuple(self.skipped),
            cancelled=cancelled,
        )
