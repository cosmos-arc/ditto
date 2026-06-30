"""Local-fill amendment tests for reconciliation repair execution."""

from __future__ import annotations

from dataclasses import replace

from _reconciliation_executor_helpers import (
    _amend_plan,
    _FakeFillAmendmentSource,
    _FakeLocalFillStore,
    _fill_record,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    AmendLocalFillRepairHandler,
    RepairActionExecutor,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorAmend:
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
