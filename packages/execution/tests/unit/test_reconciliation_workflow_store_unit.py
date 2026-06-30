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

    def test_claimed_manual_action_records_execution_result(
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
        claimed = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker",
            claimed_at="2026-05-31T09:44:00Z",
        )

        executed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker",
            result="imported fill",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-001:0001")
        assert claimed is not None
        assert executed is True
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker"
        assert record.execution_result == "imported fill"

    def test_approved_manual_action_can_be_claimed_for_execution_once(
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

        claimed = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker-a",
        )
        competed = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker-b",
        )

        record = store.get_action("rec-001:0001")
        assert claimed is not None
        assert claimed.status is RepairActionStatus.EXECUTING
        assert claimed.executor == "repair-worker-a"
        assert competed is None
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTING
        assert record.executor == "repair-worker-a"
        assert record.claimed_at is None

    def test_stale_in_flight_action_can_be_reclaimed_for_execution(
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
        first_claim = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )

        early_competition = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:46:00Z",
            reclaim_before="2026-05-31T09:44:59Z",
        )
        stale_reclaim = store.claim_for_execution(
            "rec-001:0001",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:50:00Z",
            reclaim_before="2026-05-31T09:46:00Z",
        )
        stale_owner_mark = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker-a",
            result="late stale worker result",
            executed_at="2026-05-31T09:51:00Z",
        )

        record = store.get_action("rec-001:0001")
        assert first_claim is not None
        assert first_claim.executor == "repair-worker-a"
        assert first_claim.claimed_at == "2026-05-31T09:45:00Z"
        assert early_competition is None
        assert stale_reclaim is not None
        assert stale_reclaim.status is RepairActionStatus.EXECUTING
        assert stale_reclaim.executor == "repair-worker-b"
        assert stale_reclaim.claimed_at == "2026-05-31T09:50:00Z"
        assert stale_owner_mark is False
        assert record is not None
        assert record.executor == "repair-worker-b"
        assert record.claimed_at == "2026-05-31T09:50:00Z"

    def test_same_fill_amendment_cannot_be_claimed_across_reports_while_in_flight(
        self, sqlite_client: SQLiteClient
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

        first_claim = store.claim_for_execution(
            "rec-amend-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        competing_claim = store.claim_for_execution(
            "rec-amend-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:45:01Z",
        )
        released = store.release_execution_claim(
            "rec-amend-a:0000",
            executor="repair-worker-a",
        )
        later_claim = store.claim_for_execution(
            "rec-amend-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:46:00Z",
        )

        blocked_record = store.get_action("rec-amend-b:0000")
        assert first_claim is not None
        assert first_claim.status is RepairActionStatus.EXECUTING
        assert competing_claim is None
        assert released is True
        assert later_claim is not None
        assert later_claim.status is RepairActionStatus.EXECUTING
        assert later_claim.executor == "repair-worker-b"
        assert blocked_record is not None
        assert blocked_record.status is RepairActionStatus.EXECUTING
        assert blocked_record.executor == "repair-worker-b"

    def test_same_fill_import_blocks_amend_claim_across_reports_while_in_flight(
        self, sqlite_client: SQLiteClient
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

        first_claim = store.claim_for_execution(
            "rec-import-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        competing_claim = store.claim_for_execution(
            "rec-amend-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:45:01Z",
        )
        released = store.release_execution_claim(
            "rec-import-a:0000",
            executor="repair-worker-a",
        )
        later_claim = store.claim_for_execution(
            "rec-amend-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:46:00Z",
        )

        blocked_record = store.get_action("rec-amend-b:0000")
        assert first_claim is not None
        assert first_claim.status is RepairActionStatus.EXECUTING
        assert competing_claim is None
        assert released is True
        assert later_claim is not None
        assert later_claim.status is RepairActionStatus.EXECUTING
        assert later_claim.executor == "repair-worker-b"
        assert blocked_record is not None
        assert blocked_record.status is RepairActionStatus.EXECUTING
        assert blocked_record.executor == "repair-worker-b"

    def test_stale_same_fill_import_claim_can_be_replaced_by_amend_claim(
        self, sqlite_client: SQLiteClient
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
        first_claim = store.claim_for_execution(
            "rec-import-a:0000",
            executor="stalled-repair-worker",
            claimed_at="2026-05-31T09:45:00Z",
        )

        replacement_claim = store.claim_for_execution(
            "rec-amend-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:50:00Z",
            reclaim_before="2026-05-31T09:46:00Z",
        )
        stale_owner_mark = store.mark_executed(
            "rec-import-a:0000",
            executor="stalled-repair-worker",
            result="late stale import",
            executed_at="2026-05-31T09:51:00Z",
        )

        stale_record = store.get_action("rec-import-a:0000")
        replacement_record = store.get_action("rec-amend-b:0000")
        assert first_claim is not None
        assert replacement_claim is not None
        assert replacement_claim.status is RepairActionStatus.EXECUTING
        assert replacement_claim.executor == "repair-worker-b"
        assert stale_owner_mark is False
        assert stale_record is not None
        assert stale_record.status is RepairActionStatus.APPROVED
        assert stale_record.executor is None
        assert stale_record.claimed_at is None
        assert replacement_record is not None
        assert replacement_record.status is RepairActionStatus.EXECUTING
        assert replacement_record.executor == "repair-worker-b"

    def test_same_fill_amendment_blocks_import_claim_across_reports_while_in_flight(
        self, sqlite_client: SQLiteClient
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

        first_claim = store.claim_for_execution(
            "rec-amend-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        competing_claim = store.claim_for_execution(
            "rec-import-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:45:01Z",
        )
        released = store.release_execution_claim(
            "rec-amend-a:0000",
            executor="repair-worker-a",
        )
        later_claim = store.claim_for_execution(
            "rec-import-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:46:00Z",
        )

        blocked_record = store.get_action("rec-import-b:0000")
        assert first_claim is not None
        assert first_claim.status is RepairActionStatus.EXECUTING
        assert competing_claim is None
        assert released is True
        assert later_claim is not None
        assert later_claim.status is RepairActionStatus.EXECUTING
        assert later_claim.executor == "repair-worker-b"
        assert blocked_record is not None
        assert blocked_record.status is RepairActionStatus.EXECUTING
        assert blocked_record.executor == "repair-worker-b"

    def test_same_fill_import_cannot_be_claimed_across_reports_while_in_flight(
        self, sqlite_client: SQLiteClient
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

        first_claim = store.claim_for_execution(
            "rec-import-a:0000",
            executor="repair-worker-a",
            claimed_at="2026-05-31T09:45:00Z",
        )
        competing_claim = store.claim_for_execution(
            "rec-import-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:45:01Z",
        )
        released = store.release_execution_claim(
            "rec-import-a:0000",
            executor="repair-worker-a",
        )
        later_claim = store.claim_for_execution(
            "rec-import-b:0000",
            executor="repair-worker-b",
            claimed_at="2026-05-31T09:46:00Z",
        )

        blocked_record = store.get_action("rec-import-b:0000")
        assert first_claim is not None
        assert first_claim.status is RepairActionStatus.EXECUTING
        assert competing_claim is None
        assert released is True
        assert later_claim is not None
        assert later_claim.status is RepairActionStatus.EXECUTING
        assert later_claim.executor == "repair-worker-b"
        assert blocked_record is not None
        assert blocked_record.status is RepairActionStatus.EXECUTING
        assert blocked_record.executor == "repair-worker-b"

    def test_in_flight_action_can_only_be_marked_by_claim_owner(
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
        store.claim_for_execution("rec-001:0001", executor="repair-worker-a")

        competed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker-b",
            result="competing import",
            executed_at="2026-05-31T09:45:01Z",
        )
        executed = store.mark_executed(
            "rec-001:0001",
            executor="repair-worker-a",
            result="imported fill",
            executed_at="2026-05-31T09:45:00Z",
        )

        record = store.get_action("rec-001:0001")
        assert competed is False
        assert executed is True
        assert record is not None
        assert record.status is RepairActionStatus.EXECUTED
        assert record.executor == "repair-worker-a"
        assert record.execution_result == "imported fill"

    def test_release_execution_claim_restores_manual_action_to_approved(
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
        store.claim_for_execution("rec-001:0001", executor="repair-worker-a")

        competed = store.release_execution_claim(
            "rec-001:0001",
            executor="repair-worker-b",
        )
        released = store.release_execution_claim(
            "rec-001:0001",
            executor="repair-worker-a",
        )

        record = store.get_action("rec-001:0001")
        assert competed is False
        assert released is True
        assert record is not None
        assert record.status is RepairActionStatus.APPROVED
        assert record.executor is None

    def test_release_execution_claim_restores_auto_action_to_ready(
        self, sqlite_client: SQLiteClient
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(_plan(), created_at="2026-05-31T09:30:00Z")
        store.claim_for_execution("rec-001:0000", executor="repair-worker")

        released = store.release_execution_claim(
            "rec-001:0000",
            executor="repair-worker",
        )

        record = store.get_action("rec-001:0000")
        assert released is True
        assert record is not None
        assert record.status is RepairActionStatus.READY
        assert record.executor is None

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
