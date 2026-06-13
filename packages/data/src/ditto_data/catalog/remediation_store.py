"""SQLite-backed catalog remediation approval state store."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.remediation import (
    CatalogRemediationApproval,
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalEventAction,
    CatalogRemediationApprovalStatus,
)

__all__ = ["SQLiteCatalogRemediationApprovalStore"]


class SQLiteCatalogRemediationApprovalStore:
    """Durable current-state and audit store for remediation approvals."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_remediation_approvals (
                approval_id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                intent_type TEXT NOT NULL,
                method TEXT,
                path TEXT,
                request_payload TEXT NOT NULL,
                notes TEXT,
                decided_by TEXT,
                decided_at TEXT,
                decision_notes TEXT
            )
            """,
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_remediation_approvals_item
            ON catalog_remediation_approvals(item_id, status, requested_at)
            """,
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_remediation_approval_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                action_at TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT
            )
            """,
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_remediation_approval_events
            ON catalog_remediation_approval_events(approval_id, event_id)
            """,
        )
        self._client.commit()

    def upsert_remediation_approval(
        self,
        approval: CatalogRemediationApproval,
    ) -> None:
        """Insert or replace current remediation approval state."""
        try:
            self._client.execute(
                """
                INSERT INTO catalog_remediation_approvals (
                    approval_id,
                    item_id,
                    action,
                    status,
                    requested_by,
                    requested_at,
                    intent_type,
                    method,
                    path,
                    request_payload,
                    notes,
                    decided_by,
                    decided_at,
                    decision_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (approval_id)
                DO UPDATE SET
                    item_id = excluded.item_id,
                    action = excluded.action,
                    status = excluded.status,
                    requested_by = excluded.requested_by,
                    requested_at = excluded.requested_at,
                    intent_type = excluded.intent_type,
                    method = excluded.method,
                    path = excluded.path,
                    request_payload = excluded.request_payload,
                    notes = excluded.notes,
                    decided_by = excluded.decided_by,
                    decided_at = excluded.decided_at,
                    decision_notes = excluded.decision_notes
                """,
                [
                    approval.approval_id,
                    approval.item_id,
                    approval.action,
                    approval.status,
                    approval.requested_by,
                    approval.requested_at.isoformat(),
                    approval.intent_type,
                    approval.method,
                    approval.path,
                    json.dumps(approval.request_payload, sort_keys=True),
                    approval.notes,
                    approval.decided_by,
                    approval.decided_at.isoformat()
                    if approval.decided_at is not None
                    else None,
                    approval.decision_notes,
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def append_remediation_approval_event(
        self,
        event: CatalogRemediationApprovalEvent,
    ) -> None:
        """Append a remediation approval state transition event."""
        try:
            self._client.execute(
                """
                INSERT INTO catalog_remediation_approval_events (
                    approval_id,
                    action,
                    actor,
                    action_at,
                    status,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    event.approval_id,
                    event.action,
                    event.actor,
                    event.action_at.isoformat(),
                    event.status,
                    event.notes,
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def get_remediation_approval(
        self,
        approval_id: str,
    ) -> CatalogRemediationApproval | None:
        """Return one remediation approval state by ID."""
        row = self._client.fetchone(
            """
            SELECT
                approval_id,
                item_id,
                action,
                status,
                requested_by,
                requested_at,
                intent_type,
                method,
                path,
                request_payload,
                notes,
                decided_by,
                decided_at,
                decision_notes
            FROM catalog_remediation_approvals
            WHERE approval_id = ?
            """,
            [approval_id],
        )
        if row is None:
            return None
        return _approval_from_row(row)

    def list_remediation_approvals(
        self,
        *,
        item_id: str | None = None,
        status: CatalogRemediationApprovalStatus | None = None,
    ) -> tuple[CatalogRemediationApproval, ...]:
        """Return remediation approval states filtered by item or status."""
        query = _list_approvals_query(item_id=item_id, status=status)
        params = _list_approvals_params(item_id=item_id, status=status)
        rows = self._client.fetchall(
            query,
            params,
        )
        return tuple(_approval_from_row(row) for row in rows)

    def list_remediation_approval_events(
        self,
        approval_id: str,
    ) -> tuple[CatalogRemediationApprovalEvent, ...]:
        """Return append-only events for one remediation approval."""
        rows = self._client.fetchall(
            """
            SELECT
                approval_id,
                action,
                actor,
                action_at,
                status,
                notes
            FROM catalog_remediation_approval_events
            WHERE approval_id = ?
            ORDER BY event_id
            """,
            [approval_id],
        )
        return tuple(_event_from_row(row) for row in rows)


def _approval_from_row(row: dict[str, Any]) -> CatalogRemediationApproval:
    return CatalogRemediationApproval(
        approval_id=str(row["approval_id"]),
        item_id=str(row["item_id"]),
        action=str(row["action"]),
        status=cast(CatalogRemediationApprovalStatus, str(row["status"])),
        requested_by=str(row["requested_by"]),
        requested_at=datetime.fromisoformat(str(row["requested_at"])),
        intent_type=str(row["intent_type"]),
        method=str(row["method"]) if row["method"] is not None else None,
        path=str(row["path"]) if row["path"] is not None else None,
        request_payload=cast(
            dict[str, object],
            json.loads(str(row["request_payload"])),
        ),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        decided_by=str(row["decided_by"]) if row["decided_by"] is not None else None,
        decided_at=datetime.fromisoformat(str(row["decided_at"]))
        if row["decided_at"] is not None
        else None,
        decision_notes=str(row["decision_notes"])
        if row["decision_notes"] is not None
        else None,
    )


def _list_approvals_query(
    *,
    item_id: str | None,
    status: CatalogRemediationApprovalStatus | None,
) -> str:
    base = """
        SELECT
            approval_id,
            item_id,
            action,
            status,
            requested_by,
            requested_at,
            intent_type,
            method,
            path,
            request_payload,
            notes,
            decided_by,
            decided_at,
            decision_notes
        FROM catalog_remediation_approvals
    """
    order = "ORDER BY requested_at, approval_id"
    if item_id is not None and status is not None:
        return f"{base} WHERE item_id = ? AND status = ? {order}"
    if item_id is not None:
        return f"{base} WHERE item_id = ? {order}"
    if status is not None:
        return f"{base} WHERE status = ? {order}"
    return f"{base} {order}"


def _list_approvals_params(
    *,
    item_id: str | None,
    status: CatalogRemediationApprovalStatus | None,
) -> list[str]:
    if item_id is not None and status is not None:
        return [item_id, status]
    if item_id is not None:
        return [item_id]
    if status is not None:
        return [status]
    return []


def _event_from_row(row: dict[str, Any]) -> CatalogRemediationApprovalEvent:
    return CatalogRemediationApprovalEvent(
        approval_id=str(row["approval_id"]),
        action=cast(CatalogRemediationApprovalEventAction, str(row["action"])),
        actor=str(row["actor"]),
        action_at=datetime.fromisoformat(str(row["action_at"])),
        status=cast(CatalogRemediationApprovalStatus, str(row["status"])),
        notes=str(row["notes"]) if row["notes"] is not None else None,
    )
