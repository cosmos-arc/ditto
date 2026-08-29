"""SQLite adapter for exact, terminal-run Agent raw-content cleanup."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ditto_agent._canonical import canonical_sha256
from ditto_agent.retention import (
    RawContentCandidate,
    RetentionExecutionResult,
    RetentionPlan,
    RetentionPlanConflict,
)
from ditto_agent.storage.sqlite._codec import datetime_from_epoch_us, epoch_us
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import AgentPersistenceError

_TARGET_KIND = "run_continuation"
_RUN_TARGET_KIND = "run"
_SESSION_TARGET_KIND = "session"
_TERMINAL_STATUSES = ("completed", "failed", "cancelled")
_DEFAULT_BATCH_LIMIT = 1_000
_MAX_BATCH_LIMIT = 10_000
_CANDIDATE_QUERY = """
    SELECT
        c.run_id,
        c.payload_hash,
        c.updated_at_us
    FROM agent_run_continuations AS c
    JOIN agent_runs AS r ON r.run_id = c.run_id
    JOIN agent_sessions AS s ON s.session_id = r.session_id
    WHERE c.updated_at_us <= ?
      AND r.status IN (?, ?, ?)
      AND s.retention_class <> 'audit'
      AND NOT EXISTS (
          SELECT 1
          FROM agent_retention AS m
          WHERE (
              (m.target_kind = ? AND m.target_id = c.run_id)
              OR (m.target_kind = ? AND m.target_id = r.run_id)
              OR (m.target_kind = ? AND m.target_id = s.session_id)
          )
          AND (
              m.legal_hold = 1
              OR m.retention_class = 'audit'
              OR (m.retain_until_us IS NOT NULL AND m.retain_until_us > ?)
          )
      )
    ORDER BY c.updated_at_us ASC, c.run_id ASC
    LIMIT ?
"""
_DELETE_CANDIDATE_QUERY = """
    DELETE FROM agent_run_continuations
    WHERE run_id=?
      AND payload_hash=?
      AND updated_at_us=?
      AND updated_at_us <= ?
      AND EXISTS (
          SELECT 1
          FROM agent_runs AS r
          JOIN agent_sessions AS s ON s.session_id = r.session_id
          WHERE r.run_id = agent_run_continuations.run_id
            AND r.status IN (?, ?, ?)
            AND s.retention_class <> 'audit'
            AND NOT EXISTS (
                SELECT 1
                FROM agent_retention AS m
                WHERE (
                    (
                        m.target_kind = ?
                        AND m.target_id = agent_run_continuations.run_id
                    )
                    OR (m.target_kind = ? AND m.target_id = r.run_id)
                    OR (m.target_kind = ? AND m.target_id = s.session_id)
                )
                AND (
                    m.legal_hold = 1
                    OR m.retention_class = 'audit'
                    OR (
                        m.retain_until_us IS NOT NULL
                        AND m.retain_until_us > ?
                    )
                )
            )
      )
"""


def _row_candidate(row: sqlite3.Row) -> RawContentCandidate:
    return RawContentCandidate(
        target_kind=_TARGET_KIND,
        target_id=str(row["run_id"]),
        content_hash=str(row["payload_hash"]),
        stored_at=datetime_from_epoch_us(
            int(row["updated_at_us"]),
            field="retention stored_at",
        ),
    )


class SQLiteRawContentRetentionStore:
    """Delete only exact continuation rows; never traverse a filesystem path."""

    def __init__(
        self,
        database: AgentDatabase,
        *,
        batch_limit: int = _DEFAULT_BATCH_LIMIT,
    ) -> None:
        if isinstance(batch_limit, bool) or not 1 <= batch_limit <= _MAX_BATCH_LIMIT:
            raise ValueError("retention batch_limit must be between 1 and 10000")
        self._database = database
        self._batch_limit = batch_limit

    def list_candidates(
        self,
        *,
        cutoff: datetime,
        as_of: datetime,
    ) -> tuple[RawContentCandidate, ...]:
        """Resolve only terminal, non-audit, non-held continuation rows."""
        cutoff_us = epoch_us(cutoff, field="retention cutoff")
        as_of_us = epoch_us(as_of, field="retention as_of")
        try:
            with self._database.connection() as connection:
                rows = connection.execute(
                    _CANDIDATE_QUERY,
                    (
                        cutoff_us,
                        *_TERMINAL_STATUSES,
                        _TARGET_KIND,
                        _RUN_TARGET_KIND,
                        _SESSION_TARGET_KIND,
                        as_of_us,
                        self._batch_limit,
                    ),
                ).fetchall()
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent retention query failed",
                reason_code="agent_retention_query_failed",
            ) from exc
        return tuple(_row_candidate(row) for row in rows)

    def delete_candidates(
        self,
        *,
        plan: RetentionPlan,
        approval_id: str,
        executed_at: datetime,
    ) -> RetentionExecutionResult:
        """Recheck every row and atomically delete the exact approved hashes."""
        cutoff_us = epoch_us(plan.cutoff, field="retention cutoff")
        as_of_us = epoch_us(plan.as_of, field="retention as_of")
        audit_payload_hash = canonical_sha256(
            {
                "schema_id": "agent-retention-execution-authorization",
                "schema_version": 1,
                "plan_hash": plan.plan_hash,
                "approval_id": approval_id,
            }
        )
        deleted: list[str] = []
        try:
            with self._database.transaction() as connection:
                for candidate in plan.candidates:
                    stored_at_us = epoch_us(
                        candidate.stored_at,
                        field="retention candidate stored_at",
                    )
                    cursor = connection.execute(
                        _DELETE_CANDIDATE_QUERY,
                        (
                            candidate.target_id,
                            candidate.content_hash,
                            stored_at_us,
                            cutoff_us,
                            *_TERMINAL_STATUSES,
                            _TARGET_KIND,
                            _RUN_TARGET_KIND,
                            _SESSION_TARGET_KIND,
                            as_of_us,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RetentionPlanConflict(
                            "retention candidate changed after dry-run"
                        )
                    deleted.append(candidate.target_id)
                append_audit_event(
                    connection,
                    category="retention",
                    subject_id=plan.plan_hash,
                    action="raw_content_deleted",
                    payload_hash=audit_payload_hash,
                    occurred_at=executed_at,
                )
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent retention cleanup failed",
                reason_code="agent_retention_cleanup_failed",
            ) from exc
        return RetentionExecutionResult(
            plan_hash=plan.plan_hash,
            approval_id=approval_id,
            deleted_target_ids=tuple(deleted),
            audit_payload_hash=audit_payload_hash,
            executed_at=executed_at,
        )


__all__ = ["SQLiteRawContentRetentionStore"]
