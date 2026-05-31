"""Tests for reconciliation repair action execution orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    BrokerRefreshRepairHandler,
    RepairActionExecutor,
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
