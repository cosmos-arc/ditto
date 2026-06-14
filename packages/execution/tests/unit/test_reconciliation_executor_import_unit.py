"""Broker-fill import tests for reconciliation repair execution."""

from __future__ import annotations

from _reconciliation_executor_helpers import (
    _FakeAuditSink,
    _FakeBrokerFillImportSource,
    _FakeLocalFillStore,
    _fill_record,
    _plan,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    ImportBrokerFillRepairHandler,
    RepairActionExecutor,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorImport:
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
