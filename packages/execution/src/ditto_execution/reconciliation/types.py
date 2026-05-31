"""对账数据类型 — 差异枚举、差异条目、对账报告。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ditto_execution.orders.status import OrderStatus

__all__ = [
    "MismatchType",
    "ReconciliationDiff",
    "ReconciliationReport",
    "RepairAction",
    "RepairActionRecord",
    "RepairActionStatus",
    "RepairActionType",
    "RepairExecutionResult",
    "RepairPlan",
]


class MismatchType(StrEnum):
    """对账差异类型。"""

    MISSING_FILL = "missing_fill"
    EXTRA_FILL = "extra_fill"
    QTY_MISMATCH = "qty_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    STATUS_MISMATCH = "status_mismatch"


class RepairActionType(StrEnum):
    """对账修复计划动作类型。"""

    REFRESH_BROKER_ORDER = "refresh_broker_order"
    IMPORT_BROKER_FILL = "import_broker_fill"
    AMEND_LOCAL_FILL = "amend_local_fill"
    REVIEW_ORDER_STATUS = "review_order_status"


class RepairActionStatus(StrEnum):
    """Persisted repair action workflow status."""

    READY = "ready"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass(frozen=True)
class ReconciliationDiff:
    """单条对账差异记录 — 描述期望与实际的偏差。"""

    mismatch_type: MismatchType
    order_id: str
    fill_id: str | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
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
    diff_count: int = 0
    status: Literal["matched", "mismatch", "pending"] = "pending"
    diffs: tuple[ReconciliationDiff, ...] = ()


@dataclass(frozen=True)
class RepairAction:
    """Planned reconciliation repair action with audit links."""

    action_type: RepairActionType
    mismatch_type: MismatchType
    order_id: str
    fill_id: str | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    requires_manual_review: bool = True
    reason: str = ""


@dataclass(frozen=True)
class RepairPlan:
    """Pure repair plan derived from a reconciliation report."""

    report_id: str
    account_id: str
    trade_date: str
    action_count: int
    status: Literal["not_needed", "planned"]
    requires_manual_review: bool
    actions: tuple[RepairAction, ...] = ()


@dataclass(frozen=True)
class RepairActionRecord:
    """Persisted repair action state for approval and execution tracking."""

    action_id: str
    report_id: str
    account_id: str
    trade_date: str
    action_index: int
    action_type: RepairActionType
    mismatch_type: MismatchType
    status: RepairActionStatus
    order_id: str
    fill_id: str | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    requires_manual_review: bool = True
    reason: str = ""
    reviewer: str | None = None
    review_reason: str | None = None
    reviewed_at: str | None = None
    executor: str | None = None
    execution_result: str | None = None
    executed_at: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class RepairExecutionResult:
    """Result produced by a repair action executor or handler."""

    action_id: str
    report_id: str
    trade_date: str
    action_type: RepairActionType
    order_id: str
    status: Literal["executed", "skipped", "failed"]
    message: str
    effect_count: int = 0

    @classmethod
    def executed(
        cls,
        action: RepairActionRecord,
        *,
        message: str,
        effect_count: int = 0,
    ) -> "RepairExecutionResult":
        """Build a successful repair execution result."""
        return cls(
            action_id=action.action_id,
            report_id=action.report_id,
            trade_date=action.trade_date,
            action_type=action.action_type,
            order_id=action.order_id,
            status="executed",
            message=message,
            effect_count=effect_count,
        )

    @classmethod
    def skipped(
        cls,
        action: RepairActionRecord,
        *,
        message: str,
    ) -> "RepairExecutionResult":
        """Build a non-mutating skipped repair execution result."""
        return cls(
            action_id=action.action_id,
            report_id=action.report_id,
            trade_date=action.trade_date,
            action_type=action.action_type,
            order_id=action.order_id,
            status="skipped",
            message=message,
        )
