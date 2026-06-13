"""Tests for reconciliation repair action execution orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ditto_execution.models import FillRecord
from ditto_execution.reconciliation import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairActionRecord,
    RepairActionStatus,
    RepairExecutionResult,
    RepairPlan,
    plan_repair,
)
from ditto_execution.reconciliation.executor import (
    AmendLocalFillRepairHandler,
    BrokerRefreshRepairHandler,
    ImportBrokerFillRepairHandler,
    RepairActionExecutor,
    ReviewOrderStatusRepairHandler,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_platform.foundation import SQLiteClient
from ditto_portfolio.accounting import FillEvent


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


class TestRepairActionExecutor:
    def test_ready_refresh_action_queries_broker_and_records_execution(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        broker = _FakeBrokerFillQuery((_fill("ord-refresh"),))
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "refresh_broker_order": BrokerRefreshRepairHandler(broker),
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0000",
            executed_at="2026-05-31T09:35:00Z",
        )

        record = store.get_action("rec-exec:0000")
        assert broker.queried_order_ids == ["ord-refresh"]
        assert result.status == "executed"
        assert result.effect_count == 1
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker"
        assert record.execution_result == "queried 1 broker fills"
        assert audit.results == [result]

    def test_approved_manual_action_dispatches_registered_handler(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        handled: list[str] = []
        handler = _FakeHandler(message="imported broker fill", handled=handled)
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={"import_broker_fill": handler},
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert handled == ["rec-exec:0001"]
        assert result.status == "executed"
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.execution_result == "imported broker fill"

    def test_execution_claim_prevents_reentrant_competing_dispatch(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        primary_handled: list[str] = []
        competing_handled: list[str] = []
        primary_handler = _ReentrantHandler(
            message="imported broker fill",
            handled=primary_handled,
        )
        competing_handler = _FakeHandler(
            message="competing imported broker fill",
            handled=competing_handled,
        )
        primary_audit = _FakeAuditSink()
        competing_audit = _FakeAuditSink()
        competing_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={"import_broker_fill": competing_handler},
            audit_sink=competing_audit,
            executor_id="repair-worker-b",
        )
        primary_handler.competing_executor = competing_executor
        primary_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={"import_broker_fill": primary_handler},
            audit_sink=primary_audit,
            executor_id="repair-worker-a",
        )

        result = primary_executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        competing_result = primary_handler.competing_result
        record = store.get_action("rec-exec:0001")
        assert primary_handled == ["rec-exec:0001"]
        assert competing_handled == []
        assert competing_result is not None
        assert competing_result.status == "skipped"
        assert competing_result.message == "repair action is executing"
        assert result.status == "executed"
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker-a"
        assert record.execution_result == "imported broker fill"
        assert competing_audit.results == [competing_result]
        assert primary_audit.results == [result]

    def test_stale_execution_claim_can_be_reclaimed_and_executed(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        store.claim_for_execution(
            "rec-exec:0001",
            executor="stalled-repair-worker",
            claimed_at="2026-05-31T09:45:00Z",
        )
        handled: list[str] = []
        handler = _FakeHandler(message="imported broker fill", handled=handled)
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={"import_broker_fill": handler},
            executor_id="repair-worker-b",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:50:00Z",
            reclaim_before="2026-05-31T09:46:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert handled == ["rec-exec:0001"]
        assert result.status == "executed"
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker-b"
        assert record.claimed_at == "2026-05-31T09:50:00Z"
        assert record.execution_result == "imported broker fill"

    def test_cross_report_same_fill_amendment_claim_blocks_dispatch(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _same_fill_amendment_plan("rec-amend-a", "ord-amend-a"),
            created_at="2026-05-31T09:30:00Z",
        )
        store.save_plan(
            _same_fill_amendment_plan("rec-amend-b", "ord-amend-b"),
            created_at="2026-05-31T09:31:00Z",
        )
        for action_id in ("rec-amend-a:0000", "rec-amend-b:0000"):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        store.claim_for_execution(
            "rec-amend-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        current = _fill_record(
            fill_id="fill-shared-amend",
            intent_id="ord-amend-b",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(current, quantity=100)
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({"fill-shared-amend": amended})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker-b",
        )

        result = executor.execute_action(
            "rec-amend-b:0000",
            executed_at="2026-05-31T09:45:01Z",
        )

        record = store.get_action("rec-amend-b:0000")
        assert result.status == "skipped"
        assert result.message == "repair action is blocked by another in-flight claim"
        assert source.requested_action_ids == []
        assert source.observed_current_records == []
        assert local_fills.replaced_fill_ids == []
        assert local_fills.get_fill("fill-shared-amend") == current
        assert audit.results == [result]
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED
        assert record.executor is None

    def test_cross_action_same_fill_mutation_claim_blocks_dispatch(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _same_fill_import_plan("rec-import-a", "ord-import-a"),
            created_at="2026-05-31T09:30:00Z",
        )
        store.save_plan(
            _same_fill_amendment_plan(
                "rec-amend-b",
                "ord-amend-b",
                fill_id="fill-shared-mutation",
            ),
            created_at="2026-05-31T09:31:00Z",
        )
        for action_id in ("rec-import-a:0000", "rec-amend-b:0000"):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        store.claim_for_execution(
            "rec-import-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        current = _fill_record(
            fill_id="fill-shared-mutation",
            intent_id="ord-amend-b",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(current, quantity=100)
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({"fill-shared-mutation": amended})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker-b",
        )

        result = executor.execute_action(
            "rec-amend-b:0000",
            executed_at="2026-05-31T09:45:01Z",
        )

        record = store.get_action("rec-amend-b:0000")
        assert result.status == "skipped"
        assert result.message == "repair action is blocked by another in-flight claim"
        assert source.requested_action_ids == []
        assert source.observed_current_records == []
        assert local_fills.replaced_fill_ids == []
        assert local_fills.get_fill("fill-shared-mutation") == current
        assert audit.results == [result]
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED
        assert record.executor is None

    def test_cross_action_same_fill_amendment_blocks_import_dispatch(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _same_fill_amendment_plan(
                "rec-amend-a",
                "ord-amend-a",
                fill_id="fill-shared-mutation",
            ),
            created_at="2026-05-31T09:30:00Z",
        )
        store.save_plan(
            _same_fill_import_plan("rec-import-b", "ord-import-b"),
            created_at="2026-05-31T09:31:00Z",
        )
        for action_id in ("rec-amend-a:0000", "rec-import-b:0000"):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        store.claim_for_execution(
            "rec-amend-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        source = _FakeBrokerFillImportSource(
            {
                "fill-shared-mutation": _fill_record(
                    fill_id="fill-shared-mutation",
                    intent_id="ord-import-b",
                )
            }
        )
        local_fills = _FakeLocalFillStore()
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker-b",
        )

        result = executor.execute_action(
            "rec-import-b:0000",
            executed_at="2026-05-31T09:45:01Z",
        )

        record = store.get_action("rec-import-b:0000")
        assert result.status == "skipped"
        assert result.message == "repair action is blocked by another in-flight claim"
        assert source.requested_action_ids == []
        assert local_fills.saved_fill_ids == []
        assert local_fills.get_fill("fill-shared-mutation") is None
        assert audit.results == [result]
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED
        assert record.executor is None

    def test_cross_report_same_fill_import_claim_blocks_dispatch(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _same_fill_import_plan("rec-import-a", "ord-import-a"),
            created_at="2026-05-31T09:30:00Z",
        )
        store.save_plan(
            _same_fill_import_plan("rec-import-b", "ord-import-b"),
            created_at="2026-05-31T09:31:00Z",
        )
        for action_id in ("rec-import-a:0000", "rec-import-b:0000"):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        store.claim_for_execution(
            "rec-import-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        source = _FakeBrokerFillImportSource(
            {
                "fill-shared-mutation": _fill_record(
                    fill_id="fill-shared-mutation",
                    intent_id="ord-import-b",
                )
            }
        )
        local_fills = _FakeLocalFillStore()
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker-b",
        )

        result = executor.execute_action(
            "rec-import-b:0000",
            executed_at="2026-05-31T09:45:01Z",
        )

        record = store.get_action("rec-import-b:0000")
        assert result.status == "skipped"
        assert result.message == "repair action is blocked by another in-flight claim"
        assert source.requested_action_ids == []
        assert local_fills.saved_fill_ids == []
        assert local_fills.get_fill("fill-shared-mutation") is None
        assert audit.results == [result]
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED
        assert record.executor is None

    def test_pending_manual_action_is_not_dispatched(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        handled: list[str] = []
        handler = _FakeHandler(message="imported broker fill", handled=handled)
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={"import_broker_fill": handler},
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert handled == []
        assert result.status == "skipped"
        assert result.message == "repair action is pending_review"
        assert record is not None
        assert record.status is RepairActionStatus.PENDING_REVIEW

    def test_approved_import_action_saves_broker_fill_and_marks_executed(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_fills = _FakeLocalFillStore()
        source = _FakeBrokerFillImportSource({"fill-import": _fill_record()})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=source,
                    local_fill_store=local_fills,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert source.requested_action_ids == ["rec-exec:0001"]
        assert local_fills.saved_fill_ids == ["fill-import"]
        assert local_fills.get_fill("fill-import") == _fill_record()
        assert result.status == "executed"
        assert result.message == "imported broker fill fill-import"
        assert result.effect_count == 1
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.execution_result == "imported broker fill fill-import"

    def test_approved_import_action_is_idempotent_when_fill_already_exists(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(_fill_record())
        local_fills.saved_fill_ids.clear()
        source = _FakeBrokerFillImportSource({})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=source,
                    local_fill_store=local_fills,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert source.requested_action_ids == []
        assert local_fills.saved_fill_ids == []
        assert result.status == "executed"
        assert result.message == "broker fill fill-import already imported"
        assert result.effect_count == 0
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED

    def test_approved_import_action_failure_keeps_action_retriable(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-exec:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_fills = _FakeLocalFillStore()
        source = _FakeBrokerFillImportSource({})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-exec:0001",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-exec:0001")
        assert source.requested_action_ids == ["rec-exec:0001"]
        assert local_fills.saved_fill_ids == []
        assert result.status == "failed"
        assert result.message == "broker fill fill-import was not found"
        assert audit.results == [result]
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED

    def test_approved_amend_action_replaces_local_fill_and_marks_executed(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_amend_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-amend:0000",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        current = _fill_record(fill_id="fill-amend", intent_id="ord-amend")
        amended = replace(
            current,
            quantity=120,
            fill_price=4.25,
            notes="amended from approved reconciliation repair",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({"fill-amend": amended})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-amend:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-amend:0000")
        assert source.requested_action_ids == ["rec-amend:0000"]
        assert source.observed_current_records == [current]
        assert local_fills.saved_fill_ids == []
        assert local_fills.replaced_fill_ids == ["fill-amend"]
        assert local_fills.get_fill("fill-amend") == amended
        assert result.status == "executed"
        assert result.message == "amended local fill fill-amend"
        assert result.effect_count == 1
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.execution_result == "amended local fill fill-amend"

    def test_approved_amend_action_failure_keeps_missing_local_fill_retriable(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_amend_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-amend:0000",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        amended = _fill_record(fill_id="fill-amend", intent_id="ord-amend")
        local_fills = _FakeLocalFillStore()
        source = _FakeFillAmendmentSource({"fill-amend": amended})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-amend:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-amend:0000")
        assert source.requested_action_ids == []
        assert local_fills.replaced_fill_ids == []
        assert result.status == "failed"
        assert result.message == "local fill fill-amend was not found"
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED

    def test_approved_amend_action_failure_keeps_missing_source_retriable(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_amend_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-amend:0000",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        current = _fill_record(fill_id="fill-amend", intent_id="ord-amend")
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-amend:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-amend:0000")
        assert source.requested_action_ids == ["rec-amend:0000"]
        assert local_fills.replaced_fill_ids == []
        assert local_fills.get_fill("fill-amend") == current
        assert result.status == "failed"
        assert result.message == "amended fill fill-amend was not found"
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED

    def test_approved_status_action_updates_local_order_and_marks_executed(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_status_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-status:0000",
            reviewer="ops",
            reason="OMS and broker state checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_orders = _FakeLocalOrderStatusStore({"ord-status": "submitted"})
        source = _FakeOrderStatusReviewSource({"rec-status:0000": "filled"})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=source,
                    local_order_store=local_orders,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-status:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-status:0000")
        assert source.requested_action_ids == ["rec-status:0000"]
        assert source.observed_current_statuses == ["submitted"]
        assert local_orders.updated == [("ord-status", "filled", ("submitted",))]
        assert local_orders.get_order_status("ord-status") == "filled"
        assert result.status == "executed"
        assert result.message == "updated local order ord-status status to filled"
        assert result.effect_count == 1
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert (
            record.execution_result == "updated local order ord-status status to filled"
        )

    def test_approved_status_action_is_idempotent_when_status_already_matches(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_status_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-status:0000",
            reviewer="ops",
            reason="OMS and broker state checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_orders = _FakeLocalOrderStatusStore({"ord-status": "filled"})
        source = _FakeOrderStatusReviewSource({"rec-status:0000": "filled"})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=source,
                    local_order_store=local_orders,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-status:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-status:0000")
        assert source.requested_action_ids == ["rec-status:0000"]
        assert local_orders.updated == []
        assert result.status == "executed"
        assert (
            result.message == "local order ord-status already matched reviewed status"
        )
        assert result.effect_count == 0
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED

    def test_approved_status_action_failure_keeps_missing_local_order_retriable(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_status_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-status:0000",
            reviewer="ops",
            reason="OMS and broker state checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_orders = _FakeLocalOrderStatusStore({})
        source = _FakeOrderStatusReviewSource({"rec-status:0000": "filled"})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=source,
                    local_order_store=local_orders,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-status:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-status:0000")
        assert source.requested_action_ids == []
        assert local_orders.updated == []
        assert result.status == "failed"
        assert result.message == "local order ord-status status was not found"
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED

    def test_approved_status_action_failure_keeps_missing_review_retriable(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_status_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-status:0000",
            reviewer="ops",
            reason="OMS and broker state checked",
            reviewed_at="2026-05-31T09:40:00Z",
        )
        local_orders = _FakeLocalOrderStatusStore({"ord-status": "submitted"})
        source = _FakeOrderStatusReviewSource({})
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=source,
                    local_order_store=local_orders,
                )
            },
            executor_id="repair-worker",
        )

        result = executor.execute_action(
            "rec-status:0000",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-status:0000")
        assert source.requested_action_ids == ["rec-status:0000"]
        assert local_orders.updated == []
        assert result.status == "failed"
        assert result.message == "reviewed order status for ord-status was not found"
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED

    def test_report_sequence_executes_mixed_actions_in_plan_order(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _mixed_repair_sequence_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-sequence:0001",
            "rec-sequence:0002",
            "rec-sequence:0003",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        broker = _FakeBrokerFillQuery((_fill("ord-alpha-refresh"),))
        local_fills = _FakeLocalFillStore()
        current_fill = _fill_record(
            fill_id="fill-alpha-amend",
            intent_id="ord-alpha-amend",
        )
        amended_fill = replace(current_fill, quantity=120)
        local_fills.save_fill(current_fill)
        local_fills.saved_fill_ids.clear()
        import_source = _FakeBrokerFillImportSource(
            {
                "fill-beta-import": _fill_record(
                    fill_id="fill-beta-import",
                    intent_id="ord-beta-import",
                )
            }
        )
        amend_source = _FakeFillAmendmentSource({"fill-alpha-amend": amended_fill})
        local_orders = _FakeLocalOrderStatusStore({"ord-beta-status": "submitted"})
        status_source = _FakeOrderStatusReviewSource({"rec-sequence:0003": "filled"})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "refresh_broker_order": BrokerRefreshRepairHandler(broker),
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=import_source,
                    local_fill_store=local_fills,
                ),
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=amend_source,
                    local_fill_store=local_fills,
                ),
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=status_source,
                    local_order_store=local_orders,
                ),
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-sequence",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-sequence")
        assert [result.action_id for result in results] == [
            "rec-sequence:0000",
            "rec-sequence:0001",
            "rec-sequence:0002",
            "rec-sequence:0003",
        ]
        assert [result.status for result in results] == [
            "executed",
            "executed",
            "executed",
            "executed",
        ]
        assert broker.queried_order_ids == ["ord-alpha-refresh"]
        assert import_source.requested_action_ids == ["rec-sequence:0001"]
        assert amend_source.requested_action_ids == ["rec-sequence:0002"]
        assert status_source.requested_action_ids == ["rec-sequence:0003"]
        assert local_fills.saved_fill_ids == ["fill-beta-import"]
        assert local_fills.replaced_fill_ids == ["fill-alpha-amend"]
        assert local_orders.updated == [("ord-beta-status", "filled", ("submitted",))]
        assert audit.results == list(results)
        assert [result.client_order_id for result in results] == [
            "client-alpha-refresh",
            "client-beta-import",
            "client-alpha-amend",
            "client-beta-status",
        ]
        assert [result.broker_order_id for result in results] == [
            "broker-alpha-refresh",
            "broker-beta-import",
            "broker-alpha-amend",
            "broker-beta-status",
        ]
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]
        assert [record.broker_order_id for record in records] == [
            "broker-alpha-refresh",
            "broker-beta-import",
            "broker-alpha-amend",
            "broker-beta-status",
        ]

    def test_report_sequence_closes_duplicate_fill_amendments_without_second_write(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        current = _fill_record(
            fill_id="fill-combined-amend",
            intent_id="ord-combined-amend",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(
            current,
            quantity=100,
            fill_price=4.5,
            notes="combined quantity and price amendment",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({"fill-combined-amend": amended})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-duplicate-amend")
        assert [result.action_id for result in results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in results] == ["executed", "executed"]
        assert [result.effect_count for result in results] == [1, 0]
        assert results[1].message == (
            "local fill fill-combined-amend already amended earlier in report"
        )
        assert source.requested_action_ids == ["rec-duplicate-amend:0000"]
        assert source.observed_current_records == [current]
        assert local_fills.replaced_fill_ids == ["fill-combined-amend"]
        assert local_fills.get_fill("fill-combined-amend") == amended
        assert audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]

    def test_report_sequence_blocks_duplicate_fill_amendments_after_first_failure(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        source = _FakeFillAmendmentSource(
            {
                "fill-combined-amend": _fill_record(
                    fill_id="fill-combined-amend",
                    intent_id="ord-combined-amend",
                    quantity=100,
                    fill_price=4.5,
                )
            }
        )
        local_fills = _FakeLocalFillStore()
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-duplicate-amend")
        assert [result.action_id for result in results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in results] == ["failed", "skipped"]
        assert results[0].message == "local fill fill-combined-amend was not found"
        assert results[1].message == (
            "local fill fill-combined-amend blocked by earlier failed amendment "
            "in report"
        )
        assert source.requested_action_ids == []
        assert source.observed_current_records == []
        assert local_fills.replaced_fill_ids == []
        assert audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.APPROVED,
            RepairActionStatus.APPROVED,
        ]

    def test_report_sequence_blocks_later_same_fill_amendments_while_prior_is_in_flight(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        current = _fill_record(
            fill_id="fill-combined-amend",
            intent_id="ord-combined-amend",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(
            current,
            quantity=100,
            fill_price=4.5,
            notes="combined quantity and price amendment",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        primary_source = _ReportReentrantFillAmendmentSource(
            {"fill-combined-amend": amended}
        )
        competing_source = _FakeFillAmendmentSource({"fill-combined-amend": amended})
        primary_audit = _FakeAuditSink()
        competing_audit = _FakeAuditSink()
        competing_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=competing_source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=competing_audit,
            executor_id="repair-worker-b",
        )
        primary_source.competing_executor = competing_executor
        primary_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=primary_source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=primary_audit,
            executor_id="repair-worker-a",
        )

        results = primary_executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        competing_results = primary_source.competing_results
        records = store.list_actions("rec-duplicate-amend")
        assert competing_results is not None
        assert [result.action_id for result in competing_results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in competing_results] == [
            "skipped",
            "skipped",
        ]
        assert competing_results[0].message == "repair action is executing"
        assert competing_results[1].message == (
            "local fill fill-combined-amend blocked by earlier in-flight amendment "
            "in report"
        )
        assert [result.status for result in results] == ["executed", "executed"]
        assert [result.effect_count for result in results] == [1, 0]
        assert results[1].message == (
            "local fill fill-combined-amend already amended earlier in report"
        )
        assert primary_source.requested_action_ids == ["rec-duplicate-amend:0000"]
        assert primary_source.observed_current_records == [current]
        assert competing_source.requested_action_ids == []
        assert competing_source.observed_current_records == []
        assert local_fills.replaced_fill_ids == ["fill-combined-amend"]
        assert local_fills.get_fill("fill-combined-amend") == amended
        assert competing_audit.results == list(competing_results)
        assert primary_audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]
