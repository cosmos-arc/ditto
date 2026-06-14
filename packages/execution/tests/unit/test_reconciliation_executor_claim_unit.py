"""Claim / reentrant / cross-action claim tests for reconciliation repair execution."""

from __future__ import annotations

from dataclasses import replace

from _reconciliation_executor_helpers import (
    _FakeAuditSink,
    _FakeBrokerFillImportSource,
    _FakeFillAmendmentSource,
    _FakeHandler,
    _FakeLocalFillStore,
    _fill_record,
    _plan,
    _ReentrantHandler,
    _same_fill_amendment_plan,
    _same_fill_import_plan,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    AmendLocalFillRepairHandler,
    ImportBrokerFillRepairHandler,
    RepairActionExecutor,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorClaim:
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
