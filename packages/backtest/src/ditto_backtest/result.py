"""Backtest engine result model."""

from __future__ import annotations

from dataclasses import dataclass, field

from ditto_execution.orders.model import Order
from ditto_portfolio.accounting import AccountView, FillEvent

from ditto_backtest.manifest import RunManifest

__all__ = ["EngineResult"]


@dataclass
class EngineResult:
    """
    引擎运行结果 -- 可变, 运行过程中累积.

    Attributes:
        run_id: 运行唯一 ID
        period: (start_date, end_date)
        final_nav: 最终净值
        total_trades: 总成交笔数
        orders: 所有提交的订单
        fills: 所有成交事件
        account_view: 最终账户快照
        manifest: 运行清单 (None = 未启用 RuleRefCollector)
        skipped_dates: Step 失败被跳过的日期

    """

    run_id: str
    period: tuple[str, str]
    final_nav: float = 0.0
    total_trades: int = 0
    orders: list[Order] = field(default_factory=list)
    fills: list[FillEvent] = field(default_factory=list)
    account_view: AccountView | None = None
    manifest: RunManifest | None = None
    skipped_dates: tuple[str, ...] = ()
    cancelled: bool = False
