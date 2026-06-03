"""Tests for persisted reconciliation repair execution audit records."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import FrozenInstanceError

import orjson
import pytest
from ditto_execution.audit import ExecutionAuditService, ExecutionRepairAuditSink
from ditto_execution.audit.models import AuditRecordType, RepairExecutionPayload
from ditto_execution.reconciliation.executor import RepairActionExecutor
from ditto_execution.reconciliation.types import (
    MismatchType,
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
    RepairExecutionResult,
)
from ditto_platform.foundation import SQLitePool


@pytest.fixture
def audit_service(tmp_path: object) -> Generator[ExecutionAuditService]:
    """Create an ExecutionAuditService with a temporary SQLite database."""
    pool = SQLitePool(str(tmp_path / "test_audit_repair_execution.db"))
    service = ExecutionAuditService(pool)
    service.init_schema()
    yield service
    pool.close()


def _payload(
    *,
    status: str = "executed",
    message: str = "imported broker fill fill-001",
) -> RepairExecutionPayload:
    return RepairExecutionPayload(
        trade_date="2026-05-31",
        report_id="rec-001",
        action_id="rec-001:0",
        action_type="import_broker_fill",
        order_id="ord-001",
        fill_id="fill-001",
        status=status,
        message=message,
        effect_count=1,
        correlation_id="rec-001:0",
    )


def _action() -> RepairActionRecord:
    return RepairActionRecord(
        action_id="rec-001:0",
        report_id="rec-001",
        account_id="acct-001",
        trade_date="2026-05-31",
        action_index=0,
        action_type=RepairActionType.IMPORT_BROKER_FILL,
        mismatch_type=MismatchType.EXTRA_FILL,
        status=RepairActionStatus.APPROVED,
        order_id="ord-001",
        fill_id="fill-001",
        broker_order_id="broker-001",
    )


class _OneActionWorkflowStore:
    def __init__(self, action: RepairActionRecord) -> None:
        self.action = action
        self.marked: list[tuple[str, str, str]] = []

    def get_action(self, action_id: str) -> RepairActionRecord | None:
        if action_id == self.action.action_id:
            return self.action
        return None

    def mark_executed(
        self,
        action_id: str,
        *,
        executor: str,
        result: str,
        executed_at: str = "",
    ) -> bool:
        self.marked.append((action_id, executor, result))
        return True


class _ExecuteHandler:
    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        return RepairExecutionResult.executed(
            action,
            message="imported broker fill fill-001",
            effect_count=1,
        )


class TestRepairExecutionPayload:
    """Tests for RepairExecutionPayload."""

    def test_record_type_value(self) -> None:
        assert AuditRecordType.REPAIR_EXECUTION == "repair_execution"

    def test_is_frozen(self) -> None:
        payload = _payload()
        with pytest.raises(FrozenInstanceError):
            payload.message = "changed"  # type: ignore[misc]


class TestSaveRepairExecutionLog:
    """Tests for ExecutionAuditService.save_repair_execution_log()."""

    def test_saves_single_record(self, audit_service: ExecutionAuditService) -> None:
        count = audit_service.save_repair_execution_log("run-001", (_payload(),))

        assert count == 1
        rows = audit_service.query("run-001", record_type="repair_execution")
        assert len(rows) == 1
        assert rows[0]["trade_date"] == "2026-05-31"
        assert rows[0]["record_type"] == "repair_execution"
        assert rows[0]["instrument_id"] is None
        assert rows[0]["instrument_scope"] == "workflow"
        assert rows[0]["order_id"] == "ord-001"
        assert rows[0]["fill_id"] == "fill-001"
        assert rows[0]["correlation_id"] == "rec-001:0"

        payload = orjson.loads(rows[0]["payload"])
        assert payload["report_id"] == "rec-001"
        assert payload["action_id"] == "rec-001:0"
        assert payload["action_type"] == "import_broker_fill"
        assert payload["order_id"] == "ord-001"
        assert payload["fill_id"] == "fill-001"
        assert payload["status"] == "executed"
        assert payload["effect_count"] == 1
        assert payload["correlation_id"] == "rec-001:0"

    def test_empty_tuple_returns_zero(
        self, audit_service: ExecutionAuditService
    ) -> None:
        assert audit_service.save_repair_execution_log("run-001", ()) == 0


class TestExecutionRepairAuditSink:
    """Tests for adapting repair executor results to persistent audit rows."""

    def test_records_repair_execution_result(
        self,
        audit_service: ExecutionAuditService,
    ) -> None:
        result = RepairExecutionResult.executed(
            _action(),
            message="imported broker fill fill-001",
            effect_count=1,
        )
        sink = ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-001",
        )

        sink.record_repair_execution(result)

        rows = audit_service.query("run-001", record_type="repair_execution")
        assert len(rows) == 1
        payload = orjson.loads(rows[0]["payload"])
        assert payload["report_id"] == "rec-001"
        assert payload["action_id"] == "rec-001:0"
        assert payload["trade_date"] == "2026-05-31"
        assert payload["action_type"] == "import_broker_fill"
        assert payload["order_id"] == "ord-001"
        assert payload["fill_id"] == "fill-001"
        assert payload["status"] == "executed"
        assert payload["message"] == "imported broker fill fill-001"
        assert payload["effect_count"] == 1
        assert payload["correlation_id"] == "rec-001:0"
        assert rows[0]["fill_id"] == "fill-001"

    def test_repair_action_executor_writes_persistent_audit(
        self,
        audit_service: ExecutionAuditService,
    ) -> None:
        action = _action()
        workflow_store = _OneActionWorkflowStore(action)
        executor = RepairActionExecutor(
            workflow_store=workflow_store,
            handlers={RepairActionType.IMPORT_BROKER_FILL: _ExecuteHandler()},
            audit_sink=ExecutionRepairAuditSink(
                audit_service=audit_service,
                run_id="run-001",
            ),
            executor_id="repair-worker-1",
        )

        result = executor.execute_action(action.action_id)

        assert result.status == "executed"
        assert workflow_store.marked == [
            ("rec-001:0", "repair-worker-1", "imported broker fill fill-001")
        ]
        rows = audit_service.query("run-001", record_type="repair_execution")
        assert len(rows) == 1
        payload = orjson.loads(rows[0]["payload"])
        assert payload["action_id"] == "rec-001:0"
        assert payload["fill_id"] == "fill-001"
        assert payload["status"] == "executed"
        assert payload["message"] == "imported broker fill fill-001"
