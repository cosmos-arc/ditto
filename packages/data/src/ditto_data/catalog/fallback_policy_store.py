"""SQLite-backed catalog source fallback policy state store."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyEventAction,
    CatalogSourceFallbackPolicyStatus,
)

__all__ = ["SQLiteCatalogSourceFallbackPolicyStore"]


class SQLiteCatalogSourceFallbackPolicyStore:
    """Durable current-state and audit store for source fallback policies."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_source_fallback_policies (
                policy_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                default_source TEXT NOT NULL,
                selected_source TEXT NOT NULL,
                recommended_source TEXT,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                recommended_actions TEXT NOT NULL,
                reason_codes TEXT NOT NULL,
                fallback_sources TEXT NOT NULL,
                unsupported_sources TEXT NOT NULL,
                source_selection_status TEXT NOT NULL,
                source_selection_blockers TEXT NOT NULL,
                approval_required INTEGER NOT NULL,
                execution_allowed INTEGER NOT NULL,
                notes TEXT,
                decided_by TEXT,
                decided_at TEXT,
                decision_notes TEXT
            )
            """,
        )
        self._client.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_source_fallback_policies_dataset
            ON catalog_source_fallback_policies(dataset_id, status, created_at)
            """,
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_source_fallback_policy_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_catalog_source_fallback_policy_events
            ON catalog_source_fallback_policy_events(policy_id, event_id)
            """,
        )
        self._client.commit()

    def upsert_source_fallback_policy(
        self,
        policy: CatalogSourceFallbackPolicy,
    ) -> None:
        """Insert or replace current source fallback policy state."""
        try:
            self._client.execute(
                """
                INSERT INTO catalog_source_fallback_policies (
                    policy_id,
                    dataset_id,
                    namespace,
                    trade_date,
                    default_source,
                    selected_source,
                    recommended_source,
                    status,
                    created_by,
                    created_at,
                    recommended_actions,
                    reason_codes,
                    fallback_sources,
                    unsupported_sources,
                    source_selection_status,
                    source_selection_blockers,
                    approval_required,
                    execution_allowed,
                    notes,
                    decided_by,
                    decided_at,
                    decision_notes
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT (policy_id)
                DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    namespace = excluded.namespace,
                    trade_date = excluded.trade_date,
                    default_source = excluded.default_source,
                    selected_source = excluded.selected_source,
                    recommended_source = excluded.recommended_source,
                    status = excluded.status,
                    created_by = excluded.created_by,
                    created_at = excluded.created_at,
                    recommended_actions = excluded.recommended_actions,
                    reason_codes = excluded.reason_codes,
                    fallback_sources = excluded.fallback_sources,
                    unsupported_sources = excluded.unsupported_sources,
                    source_selection_status = excluded.source_selection_status,
                    source_selection_blockers = excluded.source_selection_blockers,
                    approval_required = excluded.approval_required,
                    execution_allowed = excluded.execution_allowed,
                    notes = excluded.notes,
                    decided_by = excluded.decided_by,
                    decided_at = excluded.decided_at,
                    decision_notes = excluded.decision_notes
                """,
                [
                    policy.policy_id,
                    policy.dataset_id,
                    policy.namespace,
                    policy.trade_date,
                    policy.default_source,
                    policy.selected_source,
                    policy.recommended_source,
                    policy.status,
                    policy.created_by,
                    policy.created_at.isoformat(),
                    _json_tuple(policy.recommended_actions),
                    _json_tuple(policy.reason_codes),
                    _json_tuple(policy.fallback_sources),
                    _json_tuple(policy.unsupported_sources),
                    policy.source_selection_status,
                    _json_tuple(policy.source_selection_blockers),
                    int(policy.approval_required),
                    int(policy.execution_allowed),
                    policy.notes,
                    policy.decided_by,
                    policy.decided_at.isoformat()
                    if policy.decided_at is not None
                    else None,
                    policy.decision_notes,
                ],
            )
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def append_source_fallback_policy_event(
        self,
        event: CatalogSourceFallbackPolicyEvent,
    ) -> None:
        """Append a source fallback policy state transition event."""
        try:
            self._client.execute(
                """
                INSERT INTO catalog_source_fallback_policy_events (
                    policy_id,
                    action,
                    actor,
                    action_at,
                    status,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    event.policy_id,
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

    def get_source_fallback_policy(
        self,
        policy_id: str,
    ) -> CatalogSourceFallbackPolicy | None:
        """Return one source fallback policy state by ID."""
        row = self._client.fetchone(
            """
            SELECT
                policy_id,
                dataset_id,
                namespace,
                trade_date,
                default_source,
                selected_source,
                recommended_source,
                status,
                created_by,
                created_at,
                recommended_actions,
                reason_codes,
                fallback_sources,
                unsupported_sources,
                source_selection_status,
                source_selection_blockers,
                approval_required,
                execution_allowed,
                notes,
                decided_by,
                decided_at,
                decision_notes
            FROM catalog_source_fallback_policies
            WHERE policy_id = ?
            """,
            [policy_id],
        )
        if row is None:
            return None
        return _policy_from_row(row)

    def list_source_fallback_policies(
        self,
        *,
        dataset_id: str | None = None,
        status: CatalogSourceFallbackPolicyStatus | None = None,
    ) -> tuple[CatalogSourceFallbackPolicy, ...]:
        """Return source fallback policies filtered by dataset or status."""
        rows = self._client.fetchall(
            _list_policies_query(dataset_id=dataset_id, status=status),
            _list_policies_params(dataset_id=dataset_id, status=status),
        )
        return tuple(_policy_from_row(row) for row in rows)

    def list_source_fallback_policy_events(
        self,
        policy_id: str,
    ) -> tuple[CatalogSourceFallbackPolicyEvent, ...]:
        """Return append-only events for one source fallback policy."""
        rows = self._client.fetchall(
            """
            SELECT
                policy_id,
                action,
                actor,
                action_at,
                status,
                notes
            FROM catalog_source_fallback_policy_events
            WHERE policy_id = ?
            ORDER BY event_id
            """,
            [policy_id],
        )
        return tuple(_event_from_row(row) for row in rows)


def _policy_from_row(row: dict[str, Any]) -> CatalogSourceFallbackPolicy:
    return CatalogSourceFallbackPolicy(
        policy_id=str(row["policy_id"]),
        dataset_id=str(row["dataset_id"]),
        namespace=str(row["namespace"]),
        trade_date=str(row["trade_date"]),
        default_source=str(row["default_source"]),
        selected_source=str(row["selected_source"]),
        recommended_source=str(row["recommended_source"])
        if row["recommended_source"] is not None
        else None,
        status=cast(CatalogSourceFallbackPolicyStatus, str(row["status"])),
        created_by=str(row["created_by"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        recommended_actions=_tuple_from_json(row["recommended_actions"]),
        reason_codes=_tuple_from_json(row["reason_codes"]),
        fallback_sources=_tuple_from_json(row["fallback_sources"]),
        unsupported_sources=_tuple_from_json(row["unsupported_sources"]),
        source_selection_status=str(row["source_selection_status"]),
        source_selection_blockers=_tuple_from_json(row["source_selection_blockers"]),
        approval_required=bool(row["approval_required"]),
        execution_allowed=bool(row["execution_allowed"]),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        decided_by=str(row["decided_by"]) if row["decided_by"] is not None else None,
        decided_at=datetime.fromisoformat(str(row["decided_at"]))
        if row["decided_at"] is not None
        else None,
        decision_notes=str(row["decision_notes"])
        if row["decision_notes"] is not None
        else None,
    )


def _event_from_row(row: dict[str, Any]) -> CatalogSourceFallbackPolicyEvent:
    return CatalogSourceFallbackPolicyEvent(
        policy_id=str(row["policy_id"]),
        action=cast(CatalogSourceFallbackPolicyEventAction, str(row["action"])),
        actor=str(row["actor"]),
        action_at=datetime.fromisoformat(str(row["action_at"])),
        status=cast(CatalogSourceFallbackPolicyStatus, str(row["status"])),
        notes=str(row["notes"]) if row["notes"] is not None else None,
    )


def _list_policies_query(
    *,
    dataset_id: str | None,
    status: CatalogSourceFallbackPolicyStatus | None,
) -> str:
    base = """
        SELECT
            policy_id,
            dataset_id,
            namespace,
            trade_date,
            default_source,
            selected_source,
            recommended_source,
            status,
            created_by,
            created_at,
            recommended_actions,
            reason_codes,
            fallback_sources,
            unsupported_sources,
            source_selection_status,
            source_selection_blockers,
            approval_required,
            execution_allowed,
            notes,
            decided_by,
            decided_at,
            decision_notes
        FROM catalog_source_fallback_policies
    """
    order = "ORDER BY created_at, policy_id"
    if dataset_id is not None and status is not None:
        return f"{base} WHERE dataset_id = ? AND status = ? {order}"
    if dataset_id is not None:
        return f"{base} WHERE dataset_id = ? {order}"
    if status is not None:
        return f"{base} WHERE status = ? {order}"
    return f"{base} {order}"


def _list_policies_params(
    *,
    dataset_id: str | None,
    status: CatalogSourceFallbackPolicyStatus | None,
) -> list[str]:
    if dataset_id is not None and status is not None:
        return [dataset_id, status]
    if dataset_id is not None:
        return [dataset_id]
    if status is not None:
        return [status]
    return []


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, sort_keys=True)


def _tuple_from_json(value: object) -> tuple[str, ...]:
    loaded = json.loads(str(value))
    return tuple(str(item) for item in loaded)
