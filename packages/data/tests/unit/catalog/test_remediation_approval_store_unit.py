"""Unit tests for persistent catalog remediation approval state."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ditto_data.catalog.remediation import (
    CatalogRemediationApproval,
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalReader,
    CatalogRemediationApprovalWriter,
)
from ditto_data.catalog.remediation_store import SQLiteCatalogRemediationApprovalStore
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _approval(
    approval_id: str = "approval-001",
    *,
    status: str = "requested",
) -> CatalogRemediationApproval:
    return CatalogRemediationApproval(
        approval_id=approval_id,
        item_id="maturity_governance:stock_daily",
        action="submit_or_fix_promotion_evidence",
        status=status,
        requested_by="architecture-review",
        requested_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
        intent_type="write",
        method="POST",
        path="/ingestion/catalog/promotion/evidence",
        request_payload={
            "dataset_id": "stock_daily",
            "criterion": "complete PIT/replay coverage for the dataset",
            "evidence_uri": "ditto://evidence/stock_daily/pit-replay",
            "reviewed_by": "architecture-review",
            "passed": True,
        },
        notes="request approval before persisting reviewer evidence",
    )


class TestSQLiteCatalogRemediationApprovalStore:
    """Remediation approval state must be durable and queryable."""

    def test_approval_state_survives_reopened_sqlite_connection(
        self,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "catalog.sqlite"
        approval = _approval()
        requested = CatalogRemediationApprovalEvent(
            approval_id="approval-001",
            action="requested",
            actor="architecture-review",
            action_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
            status="requested",
            notes="request approval before persisting reviewer evidence",
        )

        writer_client, writer_pool = _client(db_path)
        try:
            writer = SQLiteCatalogRemediationApprovalStore(writer_client)
            writer.upsert_remediation_approval(approval)
            writer.append_remediation_approval_event(requested)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            reader = SQLiteCatalogRemediationApprovalStore(reader_client)

            assert reader.get_remediation_approval("approval-001") == approval
            assert reader.list_remediation_approvals(
                item_id="maturity_governance:stock_daily"
            ) == (approval,)
            assert reader.list_remediation_approvals(status="requested") == (approval,)
            assert reader.list_remediation_approval_events("approval-001") == (
                requested,
            )
        finally:
            reader_pool.close()

    def test_approval_decision_updates_current_state_and_appends_audit_event(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteCatalogRemediationApprovalStore(client)
        approval = _approval()
        approved_at = datetime(2026, 6, 9, 10, 5, tzinfo=UTC)
        approved = replace(
            approval,
            status="approved",
            decided_by="lead-reviewer",
            decided_at=approved_at,
            decision_notes="evidence write is approved",
        )
        event = CatalogRemediationApprovalEvent(
            approval_id="approval-001",
            action="approved",
            actor="lead-reviewer",
            action_at=approved_at,
            status="approved",
            notes="evidence write is approved",
        )

        try:
            store.upsert_remediation_approval(approval)
            store.upsert_remediation_approval(approved)
            store.append_remediation_approval_event(event)

            assert store.get_remediation_approval("approval-001") == approved
            assert store.list_remediation_approvals(status="requested") == ()
            assert store.list_remediation_approvals(status="approved") == (approved,)
            assert store.list_remediation_approval_events("approval-001") == (event,)
        finally:
            pool.close()

    def test_completed_execution_updates_current_state_and_appends_audit_event(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteCatalogRemediationApprovalStore(client)
        approved = replace(
            _approval(status="approved"),
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
        )
        completed = replace(approved, status="completed")
        event = CatalogRemediationApprovalEvent(
            approval_id="approval-001",
            action="completed",
            actor="ops-runner",
            action_at=datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
            status="completed",
            notes="promotion evidence persisted",
        )

        try:
            store.upsert_remediation_approval(approved)
            store.upsert_remediation_approval(completed)
            store.append_remediation_approval_event(event)

            assert store.get_remediation_approval("approval-001") == completed
            assert store.list_remediation_approvals(status="approved") == ()
            assert store.list_remediation_approvals(status="completed") == (completed,)
            assert store.list_remediation_approval_events("approval-001") == (event,)
        finally:
            pool.close()

    def test_failed_execution_event_keeps_current_state_approved(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteCatalogRemediationApprovalStore(client)
        approved = replace(
            _approval(status="approved"),
            action="repair_catalog_freshness",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
        )
        event = CatalogRemediationApprovalEvent(
            approval_id="approval-001",
            action="execution_failed",
            actor="ops-runner",
            action_at=datetime(2026, 6, 9, 10, 12, tzinfo=UTC),
            status="approved",
            notes="attempt catalog freshness repair",
        )

        try:
            store.upsert_remediation_approval(approved)
            store.append_remediation_approval_event(event)

            assert store.get_remediation_approval("approval-001") == approved
            assert store.list_remediation_approvals(status="approved") == (approved,)
            assert store.list_remediation_approval_events("approval-001") == (event,)
        finally:
            pool.close()

    def test_satisfies_remediation_approval_reader_and_writer_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            store = SQLiteCatalogRemediationApprovalStore(client)

            assert isinstance(store, CatalogRemediationApprovalReader)
            assert isinstance(store, CatalogRemediationApprovalWriter)
        finally:
            pool.close()
