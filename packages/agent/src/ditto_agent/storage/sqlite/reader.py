"""Typed reader for approved Agent SQLite runtime metadata."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ditto_agent.contracts.runtime import (
    AgentSession,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.storage.sqlite._codec import (
    datetime_from_epoch_us,
    optional_datetime_from_epoch_us,
)
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    IdempotencyRecord,
    IdempotencyStatus,
    LeaseFence,
    RetentionMetadata,
    StoredAgentRun,
    StoredApproval,
    StoredRunEvent,
)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("nullable SQLite integer has an invalid runtime type")
    return value


class AgentStoreReader:
    """Read Agent-owned projections without exposing SQLite rows or a pool."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database

    def _one(self, sql: str, parameters: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            return self._database.get_connection().execute(sql, parameters).fetchone()
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent metadata read failed",
                reason_code="agent_read_failed",
            ) from exc

    def get_session(self, session_id: str) -> AgentSession | None:
        """Return one local session identity when present."""
        row = self._one(
            "SELECT * FROM agent_sessions WHERE session_id=?",
            (session_id,),
        )
        if row is None:
            return None
        return AgentSession(
            session_id=str(row["session_id"]),
            created_at=datetime_from_epoch_us(
                int(row["created_at_us"]), field="session created_at"
            ),
            retention_class=RetentionClass(str(row["retention_class"])),
        )

    def get_run(self, run_id: str) -> StoredAgentRun | None:
        """Return one non-sensitive run projection when present."""
        row = self._one("SELECT * FROM agent_runs WHERE run_id=?", (run_id,))
        if row is None:
            return None
        return StoredAgentRun(
            run_id=str(row["run_id"]),
            session_id=str(row["session_id"]),
            status=RunStatus(str(row["status"])),
            objective_hash=str(row["objective_hash"]),
            authority_hash=str(row["authority_hash"]),
            max_model_tokens=int(row["max_model_tokens"]),
            max_model_spend_usd=Decimal(str(row["max_model_spend_usd"])),
            model_profile=ModelProfile(str(row["model_profile"])),
            manifest_hash=str(row["manifest_hash"]),
            created_at=datetime_from_epoch_us(
                int(row["created_at_us"]), field="run created_at"
            ),
            started_at=optional_datetime_from_epoch_us(
                _optional_int(row["started_at_us"]), field="run started_at"
            ),
            finished_at=optional_datetime_from_epoch_us(
                _optional_int(row["finished_at_us"]), field="run finished_at"
            ),
            revision=int(row["revision"]),
        )

    def list_run_events(self, run_id: str) -> tuple[StoredRunEvent, ...]:
        """Return immutable events in exact per-run sequence order."""
        try:
            rows = (
                self._database.get_connection()
                .execute(
                    """
                SELECT * FROM agent_run_events
                WHERE run_id=?
                ORDER BY run_sequence
                """,
                    (run_id,),
                )
                .fetchall()
            )
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent run event read failed",
                reason_code="agent_read_failed",
            ) from exc
        return tuple(
            StoredRunEvent(
                event_id=int(row["event_id"]),
                run_id=str(row["run_id"]),
                run_sequence=int(row["run_sequence"]),
                event_type=str(row["event_type"]),
                payload_hash=str(row["payload_hash"]),
                occurred_at=datetime_from_epoch_us(
                    int(row["occurred_at_us"]), field="event occurred_at"
                ),
                prev_hash=(None if row["prev_hash"] is None else str(row["prev_hash"])),
                event_hash=str(row["event_hash"]),
            )
            for row in rows
        )

    def get_approval(self, request_id: str) -> StoredApproval | None:
        """Return one exact approval request and decision."""
        row = self._one(
            "SELECT * FROM agent_approvals WHERE request_id=?",
            (request_id,),
        )
        if row is None:
            return None
        return StoredApproval(
            request_id=str(row["request_id"]),
            run_id=str(row["run_id"]),
            action_hash=str(row["action_hash"]),
            action_payload=bytes(row["action_payload"]),
            status=ApprovalStatus(str(row["status"])),
            requested_at=datetime_from_epoch_us(
                int(row["requested_at_us"]), field="approval requested_at"
            ),
            expires_at=datetime_from_epoch_us(
                int(row["expires_at_us"]), field="approval expires_at"
            ),
            operator_id=(
                None if row["operator_id"] is None else str(row["operator_id"])
            ),
            reason=None if row["reason"] is None else str(row["reason"]),
            decided_at=optional_datetime_from_epoch_us(
                _optional_int(row["decided_at_us"]), field="approval decided_at"
            ),
        )

    def get_idempotency(
        self, scope: str, idempotency_key: str
    ) -> IdempotencyRecord | None:
        """Return one request identity fence."""
        row = self._one(
            """
            SELECT * FROM agent_idempotency
            WHERE scope=? AND idempotency_key=?
            """,
            (scope, idempotency_key),
        )
        if row is None:
            return None
        return IdempotencyRecord(
            scope=str(row["scope"]),
            idempotency_key=str(row["idempotency_key"]),
            request_hash=str(row["request_hash"]),
            status=IdempotencyStatus(str(row["status"])),
            result_identity=(
                None if row["result_identity"] is None else str(row["result_identity"])
            ),
            created_at=datetime_from_epoch_us(
                int(row["created_at_us"]), field="idempotency created_at"
            ),
            updated_at=datetime_from_epoch_us(
                int(row["updated_at_us"]), field="idempotency updated_at"
            ),
        )

    def get_lease(self, resource_kind: str, resource_id: str) -> LeaseFence | None:
        """Return current lease ownership even when it has expired."""
        row = self._one(
            """
            SELECT * FROM agent_leases
            WHERE resource_kind=? AND resource_id=?
            """,
            (resource_kind, resource_id),
        )
        if row is None:
            return None
        return LeaseFence(
            resource_kind=str(row["resource_kind"]),
            resource_id=str(row["resource_id"]),
            owner_token=str(row["owner_token"]),
            fence=int(row["fence"]),
            lease_until=datetime_from_epoch_us(
                int(row["lease_until_us"]), field="lease_until"
            ),
            revision=int(row["revision"]),
        )

    def get_retention(
        self, target_kind: str, target_id: str
    ) -> RetentionMetadata | None:
        """Return metadata only; no deletion target is executed here."""
        row = self._one(
            """
            SELECT * FROM agent_retention
            WHERE target_kind=? AND target_id=?
            """,
            (target_kind, target_id),
        )
        if row is None:
            return None
        return RetentionMetadata(
            target_kind=str(row["target_kind"]),
            target_id=str(row["target_id"]),
            retention_class=RetentionClass(str(row["retention_class"])),
            retain_until=optional_datetime_from_epoch_us(
                _optional_int(row["retain_until_us"]), field="retain_until"
            ),
            legal_hold=bool(int(row["legal_hold"])),
            updated_at=datetime_from_epoch_us(
                int(row["updated_at_us"]), field="retention updated_at"
            ),
        )


__all__ = ["AgentStoreReader"]
