"""Shared helpers for reconciliation executor unit tests.

Migrated verbatim from the former monolithic
``test_reconciliation_executor_unit.py`` — plan builders, fake sources/stores
and handler stubs used across the split test modules. Do not modify behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_execution.models import FillRecord
from ditto_execution.reconciliation import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairActionRecord,
    RepairExecutionResult,
    RepairPlan,
    plan_repair,
)
from ditto_execution.reconciliation.executor import RepairActionExecutor
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import FillEvent

__all__ = (
    "_FakeAuditSink",
    "_FakeBrokerFillImportSource",
    "_FakeBrokerFillQuery",
    "_FakeFillAmendmentSource",
    "_FakeHandler",
    "_FakeLocalFillStore",
    "_FakeLocalOrderStatusStore",
    "_FakeOrderStatusReviewSource",
    "_ReentrantHandler",
    "_ReportReentrantFillAmendmentSource",
    "_amend_plan",
    "_duplicate_fill_amendment_plan",
    "_fill",
    "_fill_record",
    "_mixed_repair_sequence_plan",
    "_plan",
    "_same_fill_amendment_plan",
    "_same_fill_import_plan",
    "_status_plan",
)


def _plan():
    report = ReconciliationReport(
        report_id="rec-exec",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=2,
        actual_count=2,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.MISSING_FILL,
                order_id="ord-refresh",
                client_order_id="client-refresh",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id="ord-import",
                fill_id="fill-import",
                broker_order_id="broker-import",
            ),
        ),
    )
    return plan_repair(report)


def _amend_plan():
    report = ReconciliationReport(
        report_id="rec-amend",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=1,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id="ord-amend",
                fill_id="fill-amend",
                client_order_id="client-amend",
            ),
        ),
    )
    return plan_repair(report)


def _same_fill_amendment_plan(
    report_id: str,
    order_id: str,
    *,
    fill_id: str = "fill-shared-amend",
) -> RepairPlan:
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=1,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=f"client-{order_id}",
                broker_order_id=f"broker-{order_id}",
            ),
        ),
    )
    return plan_repair(report)


def _same_fill_import_plan(
    report_id: str,
    order_id: str,
    *,
    fill_id: str = "fill-shared-mutation",
) -> RepairPlan:
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=1,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=f"client-{order_id}",
                broker_order_id=f"broker-{order_id}",
            ),
        ),
    )
    return plan_repair(report)


def _status_plan():
    report = ReconciliationReport(
        report_id="rec-status",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=1,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.STATUS_MISMATCH,
                order_id="ord-status",
                client_order_id="client-status",
            ),
        ),
    )
    return plan_repair(report)


def _mixed_repair_sequence_plan():
    report = ReconciliationReport(
        report_id="rec-sequence",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=4,
        actual_count=4,
        diff_count=4,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.MISSING_FILL,
                order_id="ord-alpha-refresh",
                client_order_id="client-alpha-refresh",
                broker_order_id="broker-alpha-refresh",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id="ord-beta-import",
                fill_id="fill-beta-import",
                client_order_id="client-beta-import",
                broker_order_id="broker-beta-import",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id="ord-alpha-amend",
                fill_id="fill-alpha-amend",
                client_order_id="client-alpha-amend",
                broker_order_id="broker-alpha-amend",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.STATUS_MISMATCH,
                order_id="ord-beta-status",
                client_order_id="client-beta-status",
                broker_order_id="broker-beta-status",
            ),
        ),
    )
    return plan_repair(report)


def _duplicate_fill_amendment_plan():
    report = ReconciliationReport(
        report_id="rec-duplicate-amend",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id="ord-combined-amend",
                fill_id="fill-combined-amend",
                client_order_id="client-combined-amend",
                broker_order_id="broker-combined-amend",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.PRICE_MISMATCH,
                order_id="ord-combined-amend",
                fill_id="fill-combined-amend",
                client_order_id="client-combined-amend",
                broker_order_id="broker-combined-amend",
            ),
        ),
    )
    return plan_repair(report)


def _fill(order_id: str) -> FillEvent:
    return FillEvent(
        fill_id=f"fill-{order_id}",
        order_id=order_id,
        instrument_id=InstrumentId(510300),
        direction=OrderSide.BUY,
        filled_quantity=100,
        fill_price=4.2,
        fee=0.0,
        slippage=0.0,
        event_time=datetime(2026, 5, 31, 1, 30, tzinfo=UTC),
        cumulative_quantity=100,
        leaves_quantity=0,
    )


class _FakeBrokerFillQuery:
    def __init__(self, fills: tuple[FillEvent, ...]) -> None:
        self.fills = fills
        self.queried_order_ids: list[str] = []

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        self.queried_order_ids.append(order_id)
        return self.fills


@dataclass
class _FakeHandler:
    message: str
    handled: list[str]

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        self.handled.append(action.action_id)
        return RepairExecutionResult.executed(
            action,
            message=self.message,
            effect_count=1,
        )


@dataclass
class _ReentrantHandler:
    message: str
    handled: list[str]
    competing_executor: RepairActionExecutor | None = None
    competing_result: RepairExecutionResult | None = None

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        self.handled.append(action.action_id)
        if self.competing_executor is None:
            raise AssertionError("competing executor not configured")
        self.competing_result = self.competing_executor.execute_action(
            action.action_id,
            executed_at="2026-05-31T09:45:01Z",
        )
        return RepairExecutionResult.executed(
            action,
            message=self.message,
            effect_count=1,
        )


class _FakeAuditSink:
    def __init__(self) -> None:
        self.results: list[RepairExecutionResult] = []

    def record_repair_execution(self, result: RepairExecutionResult) -> None:
        self.results.append(result)


def _fill_record(
    fill_id: str = "fill-import",
    *,
    intent_id: str = "ord-import",
    quantity: int = 100,
    fill_price: float = 4.2,
    notes: str = "imported from reconciliation repair",
) -> FillRecord:
    return FillRecord(
        fill_id=fill_id,
        intent_id=intent_id,
        strategy_id="acct-001",
        trade_date="2026-05-31",
        instrument_id=510300,
        direction="buy",
        quantity=quantity,
        fill_price=fill_price,
        fee=0.0,
        slippage=0.0,
        notes=notes,
        settlement_date="2026-06-01",
        created_at="2026-05-31T09:45:00Z",
    )


class _FakeBrokerFillImportSource:
    def __init__(self, fills: dict[str, FillRecord]) -> None:
        self.fills = fills
        self.requested_action_ids: list[str] = []

    def get_fill_record(self, action: RepairActionRecord) -> FillRecord | None:
        self.requested_action_ids.append(action.action_id)
        if action.fill_id is None:
            return None
        return self.fills.get(action.fill_id)


class _FakeFillAmendmentSource:
    def __init__(self, fills: dict[str, FillRecord]) -> None:
        self.fills = fills
        self.requested_action_ids: list[str] = []
        self.observed_current_records: list[FillRecord] = []

    def get_amended_fill_record(
        self,
        action: RepairActionRecord,
        current: FillRecord,
    ) -> FillRecord | None:
        self.requested_action_ids.append(action.action_id)
        self.observed_current_records.append(current)
        if action.fill_id is None:
            return None
        return self.fills.get(action.fill_id)


class _ReportReentrantFillAmendmentSource:
    def __init__(self, fills: dict[str, FillRecord]) -> None:
        self.fills = fills
        self.requested_action_ids: list[str] = []
        self.observed_current_records: list[FillRecord] = []
        self.competing_executor: RepairActionExecutor | None = None
        self.competing_results: tuple[RepairExecutionResult, ...] | None = None

    def get_amended_fill_record(
        self,
        action: RepairActionRecord,
        current: FillRecord,
    ) -> FillRecord | None:
        self.requested_action_ids.append(action.action_id)
        self.observed_current_records.append(current)
        if self.competing_executor is None:
            raise AssertionError("competing executor not configured")
        if self.competing_results is None:
            self.competing_results = self.competing_executor.execute_report_actions(
                action.report_id,
                executed_at="2026-05-31T09:45:01Z",
            )
        if action.fill_id is None:
            return None
        return self.fills.get(action.fill_id)


class _FakeLocalFillStore:
    def __init__(self) -> None:
        self.records: dict[str, FillRecord] = {}
        self.saved_fill_ids: list[str] = []
        self.replaced_fill_ids: list[str] = []

    def get_fill(self, fill_id: str) -> FillRecord | None:
        return self.records.get(fill_id)

    def save_fill(self, record: FillRecord) -> None:
        self.saved_fill_ids.append(record.fill_id)
        self.records[record.fill_id] = record

    def replace_fill(self, record: FillRecord) -> bool:
        if record.fill_id not in self.records:
            return False
        self.replaced_fill_ids.append(record.fill_id)
        self.records[record.fill_id] = record
        return True


class _FakeOrderStatusReviewSource:
    def __init__(self, statuses: dict[str, str]) -> None:
        self.statuses = statuses
        self.requested_action_ids: list[str] = []
        self.observed_current_statuses: list[str] = []

    def get_reviewed_order_status(
        self,
        action: RepairActionRecord,
        current_status: str,
    ) -> str | None:
        self.requested_action_ids.append(action.action_id)
        self.observed_current_statuses.append(current_status)
        return self.statuses.get(action.action_id)


class _FakeLocalOrderStatusStore:
    def __init__(self, statuses: dict[str, str]) -> None:
        self.statuses = statuses
        self.updated: list[tuple[str, str, tuple[str, ...]]] = []

    def get_order_status(self, order_id: str) -> str | None:
        return self.statuses.get(order_id)

    def update_order_status(
        self,
        order_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        if self.statuses.get(order_id) not in expected_current:
            return False
        self.updated.append((order_id, status, expected_current))
        self.statuses[order_id] = status
        return True
