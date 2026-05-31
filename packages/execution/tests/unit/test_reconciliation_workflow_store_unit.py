"""Tests for persisted reconciliation repair workflow state."""

from ditto_execution.reconciliation import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairActionStatus,
    RepairActionType,
    RepairPlan,
    plan_repair,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


def _plan() -> RepairPlan:
    report = ReconciliationReport(
        report_id="rec-001",
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


class TestSQLiteRepairWorkflowStore:
    def test_save_plan_persists_actions_with_default_review_state(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()

        records = store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")

        assert [record.action_id for record in records] == [
            "rec-001:0000",
            "rec-001:0001",
        ]
        assert [record.status for record in records] == [
            RepairActionStatus.READY,
            RepairActionStatus.PENDING_REVIEW,
        ]
        assert records[0].action_type is RepairActionType.REFRESH_BROKER_ORDER
        assert records[0].requires_manual_review is False
        assert records[1].action_type is RepairActionType.IMPORT_BROKER_FILL
        assert records[1].fill_id == "fill-import"
        assert records[1].broker_order_id == "broker-import"
        assert records[1].requires_manual_review is True

    def test_save_plan_is_idempotent_and_does_not_overwrite_review(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        approved = store.approve_action(
            "rec-001:0001",
            reviewer="ops",
            reason="broker statement checked",
            reviewed_at="2026-05-31T09:35:00Z",
        )

        records = store.save_plan(_plan(), created_at="2026-05-31T09:40:00Z")

        assert approved is True
        assert len(records) == 2
        assert records[1].status is RepairActionStatus.APPROVED
        assert records[1].reviewer == "ops"
        assert records[1].review_reason == "broker statement checked"

    def test_manual_action_cannot_execute_before_approval(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")

        executed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker",
            result="imported fill",
            executed_at="2026-05-31T09:45:00Z",
        )

        assert executed is False
        record = store.get_action("rec-001:0001")
        assert record is not None
        assert record.status is RepairActionStatus.PENDING_REVIEW

    def test_approved_manual_action_records_execution_result(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.approve_action(
            "rec-001:0001",
            reviewer="ops",
            reason="approved import",
            reviewed_at="2026-05-31T09:35:00Z",
        )

        executed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker",
            result="imported fill",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-001:0001")
        assert executed is True
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker"
        assert record.execution_result == "imported fill"

    def test_rejected_action_cannot_be_executed(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        rejected = store.reject_action(
            "rec-001:0001",
            reviewer="ops",
            reason="broker fill belongs to another account",
            reviewed_at="2026-05-31T09:35:00Z",
        )

        executed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker",
            result="imported fill",
            executed_at="2026-05-31T09:45:00Z",
        )

        assert rejected is True
        assert executed is False
        record = store.get_action("rec-001:0001")
        assert record is not None
        assert record.status is RepairActionStatus.REJECTED
