"""对账数据类型 — 差异枚举、差异条目、对账报告。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_execution.orders.status import OrderStatus

__all__ = ["MismatchType", "ReconciliationDiff", "ReconciliationReport"]


class MismatchType(StrEnum):
    """对账差异类型。"""

    MISSING_FILL = "missing_fill"
    EXTRA_FILL = "extra_fill"
    QTY_MISMATCH = "qty_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    STATUS_MISMATCH = "status_mismatch"


@dataclass(frozen=True)
class ReconciliationDiff:
    """单条对账差异记录 — 描述期望与实际的偏差。"""

    mismatch_type: MismatchType
    order_id: str
    fill_id: str | None = None
    expected_quantity: int | None = None
    actual_quantity: int | None = None
    expected_price: float | None = None
    actual_price: float | None = None
    expected_status: OrderStatus | None = None
    actual_status: OrderStatus | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    """Summary of expected versus actual execution records."""

    report_id: str
    account_id: str
    trade_date: str
    expected_count: int
    actual_count: int
    unmatched_count: int = 0
    status: str = "pending"
    diffs: tuple[ReconciliationDiff, ...] = ()
