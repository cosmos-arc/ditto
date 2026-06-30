"""Dispatch / broker-refresh / pending-review repair-execution tests."""

from __future__ import annotations

from _reconciliation_executor_helpers import (
    _FakeAuditSink,
    _FakeBrokerFillQuery,
    _FakeHandler,
    _fill,
    _plan,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    BrokerRefreshRepairHandler,
    RepairActionExecutor,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorDispatch:
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
