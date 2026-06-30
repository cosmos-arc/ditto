"""Order-status review / update tests for reconciliation repair execution."""

from __future__ import annotations

from _reconciliation_executor_helpers import (
    _FakeLocalOrderStatusStore,
    _FakeOrderStatusReviewSource,
    _status_plan,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    RepairActionExecutor,
    ReviewOrderStatusRepairHandler,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorStatus:
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
