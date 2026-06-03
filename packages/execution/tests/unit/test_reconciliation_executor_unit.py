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
