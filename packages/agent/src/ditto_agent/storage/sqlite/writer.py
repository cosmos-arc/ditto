"""Atomic, lease-fenced writer for Agent SQLite runtime metadata."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.contracts.approval import ApprovalRequest
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    RunStatus,
)
from ditto_agent.runtime.episode import episode_event_hash
from ditto_agent.runtime.state_machine import transition_run
from ditto_agent.storage.sqlite._codec import decimal_text, epoch_us
from ditto_agent.storage.sqlite._coordination_writer import AgentCoordinationWriter
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
    IdempotencyConflictError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    IdempotencyDisposition,
    IdempotencyRecord,
    IdempotencyReservation,
    IdempotencyStatus,
    LeaseFence,
    RetentionMetadata,
    StoredAgentRun,
    StoredApproval,
    StoredRunEvent,
)


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


def _objective_hash(objective: str) -> str:
    return hashlib.sha256(objective.encode()).hexdigest()


class AgentStoreWriter:
    """Persist exact replays and reject every identity or ownership drift."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database
        self._reader = AgentStoreReader(database)
        self._coordination = AgentCoordinationWriter(database)

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        try:
            with self._database.transaction() as connection:
                yield connection
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent metadata write failed",
                reason_code="agent_write_failed",
            ) from exc

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        category: str,
        subject_id: str,
        action: str,
        payload: object,
        occurred_at: datetime,
    ) -> None:
        append_audit_event(
            connection,
            category=category,
            subject_id=subject_id,
            action=action,
            payload_hash=canonical_sha256(payload),
            occurred_at=occurred_at,
        )

    def put_manifest(self, manifest: AgentManifest) -> None:
        """Persist one immutable manifest or accept an exact replay."""
        values = (
            manifest.manifest_hash,
            manifest.manifest_id,
            manifest.agent_version,
            manifest.prompt_version,
            manifest.prompt_hash,
            manifest.tool_schema_version,
            manifest.tool_schema_hash,
            manifest.model_profile.value,
            manifest.model_snapshot,
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_manifests WHERE manifest_hash=?",
                (manifest.manifest_hash,),
            ).fetchone()
            if row is not None:
                durable = tuple(row[name] for name in row)
                if durable != values:
                    raise _conflict(
                        "Manifest hash conflicts with durable content",
                        "agent_manifest_conflict",
                    )
                return
            connection.execute(
                """
                INSERT INTO agent_manifests (
                    manifest_hash, manifest_id, agent_version, prompt_version,
                    prompt_hash, tool_schema_version, tool_schema_hash,
                    model_profile, model_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def create_session(self, session: AgentSession) -> AgentSession:
        """Create one session or accept an exact identity replay."""
        created_at_us = epoch_us(session.created_at, field="session created_at")
        values = (session.session_id, created_at_us, session.retention_class.value)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_sessions WHERE session_id=?",
                (session.session_id,),
            ).fetchone()
            if row is not None:
                durable = (
                    row["session_id"],
                    row["created_at_us"],
                    row["retention_class"],
                )
                if durable != values:
                    raise _conflict(
                        "Session replay conflicts with durable identity",
                        "agent_session_conflict",
                    )
                return session
            connection.execute(
                """
                INSERT INTO agent_sessions (
                    session_id, created_at_us, retention_class
                ) VALUES (?, ?, ?)
                """,
                values,
            )
            self._audit(
                connection,
                category="session",
                subject_id=session.session_id,
                action="created",
                payload={
                    "session_id": session.session_id,
                    "created_at": session.created_at,
                    "retention_class": session.retention_class,
                },
                occurred_at=session.created_at,
            )
        return session

    def create_run(self, run: AgentRun) -> StoredAgentRun:
        """Create a queued run while persisting only the objective digest."""
        if run.status is not RunStatus.QUEUED:
            raise ValueError("new Agent runs must start queued")
        if run.started_at is not None or run.finished_at is not None:
            raise ValueError("new queued Agent runs cannot have lifecycle timestamps")
        objective_hash = _objective_hash(run.objective)
        values = (
            run.run_id,
            run.session_id,
            run.status.value,
            objective_hash,
            run.authority_hash,
            run.max_model_tokens,
            decimal_text(run.max_model_spend_usd),
            run.model_profile.value,
            run.manifest_hash,
            epoch_us(run.created_at, field="run created_at"),
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id=?", (run.run_id,)
            ).fetchone()
            if row is not None:
                durable = tuple(row[name] for name in row)
                expected = (*values, None, None, 0)
                if durable != expected:
                    raise _conflict(
                        "Run replay conflicts with durable identity",
                        "agent_run_conflict",
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO agent_runs (
                        run_id, session_id, status, objective_hash, authority_hash,
                        max_model_tokens, max_model_spend_usd, model_profile,
                        manifest_hash, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                self._audit(
                    connection,
                    category="run",
                    subject_id=run.run_id,
                    action="created",
                    payload={
                        "run_id": run.run_id,
                        "session_id": run.session_id,
                        "objective_hash": objective_hash,
                        "authority_hash": run.authority_hash,
                        "manifest_hash": run.manifest_hash,
                    },
                    occurred_at=run.created_at,
                )
        stored = self._reader.get_run(run.run_id)
        if stored is None:
            raise AgentPersistenceError(
                "Created Agent run is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored

    def transition_run(
        self,
        *,
        run_id: str,
        expected_revision: int,
        target: RunStatus,
        occurred_at: datetime,
        event_type: str | None = None,
        event_payload_hash: str | None = None,
    ) -> StoredAgentRun:
        """Apply one legal lifecycle transition and optional event atomically."""
        if (event_type is None) != (event_payload_hash is None):
            raise ValueError(
                "event_type and event_payload_hash must be supplied together"
            )
        if event_type is not None:
            event_type = normalized_text(event_type, field="event_type")
        if event_payload_hash is not None:
            event_payload_hash = sha256_hex(
                event_payload_hash, field="event_payload_hash"
            )
        occurred_at_us = epoch_us(occurred_at, field="transition occurred_at")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status, revision, started_at_us FROM agent_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise _conflict("Agent run does not exist", "agent_run_missing")
            revision = int(row["revision"])
            if revision != expected_revision:
                raise _conflict(
                    "Agent run revision has changed", "agent_run_revision_conflict"
                )
            source = RunStatus(str(row["status"]))
            transition_run(source, target)
            started_at_us = row["started_at_us"]
            if source is RunStatus.QUEUED and target in {
                RunStatus.RUNNING,
                RunStatus.CANCELLED,
            }:
                started_at_us = occurred_at_us
            finished_at_us = (
                occurred_at_us
                if target
                in {
                    RunStatus.COMPLETED,
                    RunStatus.FAILED,
                    RunStatus.CANCELLED,
                }
                else None
            )
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET status=?, started_at_us=?, finished_at_us=?, revision=revision + 1
                WHERE run_id=? AND revision=?
                """,
                (
                    target.value,
                    started_at_us,
                    finished_at_us,
                    run_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "Agent run transition lost its revision fence",
                    "agent_run_revision_conflict",
                )
            self._audit(
                connection,
                category="run",
                subject_id=run_id,
                action="transitioned",
                payload={
                    "source": source,
                    "target": target,
                    "revision": expected_revision + 1,
                },
                occurred_at=occurred_at,
            )
            if event_type is not None and event_payload_hash is not None:
                self._append_run_event(
                    connection,
                    run_id=run_id,
                    event_type=event_type,
                    payload_hash=event_payload_hash,
                    occurred_at=occurred_at,
                    occurred_at_us=occurred_at_us,
                )
        stored = self._reader.get_run(run_id)
        if stored is None:
            raise AgentPersistenceError(
                "Transitioned Agent run is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored

    def append_run_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload_hash: str,
        occurred_at: datetime,
    ) -> StoredRunEvent:
        """Append one event with database-assigned global and per-run sequence."""
        event_type = normalized_text(event_type, field="event_type")
        payload_hash = sha256_hex(payload_hash, field="payload_hash")
        occurred_at_us = epoch_us(occurred_at, field="event occurred_at")
        with self._transaction() as connection:
            return self._append_run_event(
                connection,
                run_id=run_id,
                event_type=event_type,
                payload_hash=payload_hash,
                occurred_at=occurred_at,
                occurred_at_us=occurred_at_us,
            )

    @staticmethod
    def _append_run_event(
        connection: sqlite3.Connection,
        *,
        run_id: str,
        event_type: str,
        payload_hash: str,
        occurred_at: datetime,
        occurred_at_us: int,
    ) -> StoredRunEvent:
        if (
            connection.execute(
                "SELECT 1 FROM agent_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            is None
        ):
            raise _conflict("Agent run does not exist", "agent_run_missing")
        last = connection.execute(
            """
            SELECT run_sequence, event_hash
            FROM agent_run_events
            WHERE run_id=?
            ORDER BY run_sequence DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        run_sequence = 1 if last is None else int(last["run_sequence"]) + 1
        prev_hash = None if last is None else str(last["event_hash"])
        global_row = connection.execute(
            "SELECT COALESCE(MAX(event_id), 0) + 1 FROM agent_run_events"
        ).fetchone()
        event_id = int(global_row[0])
        event_hash = episode_event_hash(
            event_id=event_id,
            run_id=run_id,
            run_sequence=run_sequence,
            event_type=event_type,
            payload_hash=payload_hash,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
        )
        connection.execute(
            """
            INSERT INTO agent_run_events (
                event_id, run_id, run_sequence, event_type, payload_hash,
                occurred_at_us, prev_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                run_sequence,
                event_type,
                payload_hash,
                occurred_at_us,
                prev_hash,
                event_hash,
            ),
        )
        return StoredRunEvent(
            event_id=event_id,
            run_id=run_id,
            run_sequence=run_sequence,
            event_type=event_type,
            payload_hash=payload_hash,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )

    def create_approval(
        self, request: ApprovalRequest, *, requested_at: datetime
    ) -> StoredApproval:
        """Persist canonical action state only after re-verifying its hash."""
        if not request.verify_action_hash():
            raise ValueError("approval action hash is invalid")
        requested_at_us = epoch_us(requested_at, field="approval requested_at")
        expires_at_us = epoch_us(request.expires_at, field="approval expires_at")
        if requested_at_us >= expires_at_us:
            raise ValueError("approval must be requested before its expiry")
        payload = canonical_bytes(request.action_payload())
        values = (
            request.request_id,
            request.run_id,
            request.action_hash,
            payload,
            ApprovalStatus.PENDING.value,
            requested_at_us,
            expires_at_us,
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_approvals WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if row is not None:
                durable = tuple(row[name] for name in row)
                expected = (*values, None, None, None)
                if durable != expected:
                    raise _conflict(
                        "Approval replay conflicts with durable action",
                        "agent_approval_conflict",
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO agent_approvals (
                        request_id, run_id, action_hash, action_payload, status,
                        requested_at_us, expires_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                self._audit(
                    connection,
                    category="approval",
                    subject_id=request.request_id,
                    action="requested",
                    payload={
                        "request_id": request.request_id,
                        "run_id": request.run_id,
                        "action_hash": request.action_hash,
                        "expires_at": request.expires_at,
                    },
                    occurred_at=requested_at,
                )
        stored = self._reader.get_approval(request.request_id)
        if stored is None:
            raise AgentPersistenceError(
                "Created approval is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored

    def decide_approval(
        self,
        *,
        request_id: str,
        expected_action_hash: str,
        approved: bool,
        operator_id: str,
        reason: str | None,
        decided_at: datetime,
    ) -> StoredApproval:
        """Commit one terminal decision over the exact unexpired action hash."""
        operator_id = normalized_text(operator_id, field="operator_id")
        expected_action_hash = sha256_hex(
            expected_action_hash, field="expected_action_hash"
        )
        if reason is not None:
            reason = normalized_text(reason, field="reason", maximum=4096)
        decided_at_us = epoch_us(decided_at, field="approval decided_at")
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT action_hash, status, expires_at_us
                FROM agent_approvals WHERE request_id=?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                raise _conflict("Approval does not exist", "agent_approval_missing")
            if row["action_hash"] != expected_action_hash:
                raise _conflict(
                    "Approval action hash has changed", "agent_approval_hash_conflict"
                )
            if row["status"] != ApprovalStatus.PENDING.value:
                raise _conflict(
                    "Approval already has a terminal decision",
                    "agent_approval_already_decided",
                )
            if decided_at_us >= int(row["expires_at_us"]):
                raise _conflict("Approval has expired", "agent_approval_expired")
            connection.execute(
                """
                UPDATE agent_approvals
                SET status=?, operator_id=?, reason=?, decided_at_us=?
                WHERE request_id=? AND status='pending' AND action_hash=?
                """,
                (
                    status.value,
                    operator_id,
                    reason,
                    decided_at_us,
                    request_id,
                    expected_action_hash,
                ),
            )
            self._audit(
                connection,
                category="approval",
                subject_id=request_id,
                action=status.value,
                payload={
                    "request_id": request_id,
                    "action_hash": expected_action_hash,
                    "operator_id": operator_id,
                    "status": status,
                },
                occurred_at=decided_at,
            )
        stored = self._reader.get_approval(request_id)
        if stored is None:
            raise AgentPersistenceError(
                "Decided approval is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored

    def reserve_idempotency(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        occurred_at: datetime,
    ) -> IdempotencyReservation:
        """Reserve a key or return the exact prior request record."""
        scope = normalized_text(scope, field="idempotency scope")
        idempotency_key = normalized_text(idempotency_key, field="idempotency_key")
        request_hash = sha256_hex(request_hash, field="request_hash")
        occurred_at_us = epoch_us(occurred_at, field="idempotency occurred_at")
        disposition = IdempotencyDisposition.REPLAY
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT request_hash FROM agent_idempotency
                WHERE scope=? AND idempotency_key=?
                """,
                (scope, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_hash"] != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was reused with a different request body",
                        reason_code="agent_idempotency_hash_conflict",
                    )
            else:
                disposition = IdempotencyDisposition.CREATED
                connection.execute(
                    """
                    INSERT INTO agent_idempotency (
                        scope, idempotency_key, request_hash, status,
                        created_at_us, updated_at_us
                    ) VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        scope,
                        idempotency_key,
                        request_hash,
                        occurred_at_us,
                        occurred_at_us,
                    ),
                )
                self._audit(
                    connection,
                    category="idempotency",
                    subject_id=f"{scope}:{idempotency_key}",
                    action="reserved",
                    payload={"scope": scope, "request_hash": request_hash},
                    occurred_at=occurred_at,
                )
        record = self._reader.get_idempotency(scope, idempotency_key)
        if record is None:
            raise AgentPersistenceError(
                "Reserved idempotency record is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return IdempotencyReservation(disposition=disposition, record=record)

    def complete_idempotency(
        self,
        *,
        scope: str,
        idempotency_key: str,
        expected_request_hash: str,
        result_identity: str,
        occurred_at: datetime,
    ) -> IdempotencyRecord:
        """Bind an exact pending request hash to one immutable result identity."""
        expected_request_hash = sha256_hex(
            expected_request_hash, field="expected_request_hash"
        )
        result_identity = normalized_text(result_identity, field="result_identity")
        occurred_at_us = epoch_us(occurred_at, field="idempotency occurred_at")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT request_hash, status, result_identity
                FROM agent_idempotency
                WHERE scope=? AND idempotency_key=?
                """,
                (scope, idempotency_key),
            ).fetchone()
            if row is None or row["request_hash"] != expected_request_hash:
                raise IdempotencyConflictError(
                    "Idempotency completion lost its request hash fence",
                    reason_code="agent_idempotency_hash_conflict",
                )
            if row["status"] == IdempotencyStatus.COMPLETED.value:
                if row["result_identity"] != result_identity:
                    raise IdempotencyConflictError(
                        "Idempotency result identity conflicts with durable result",
                        reason_code="agent_idempotency_result_conflict",
                    )
            else:
                connection.execute(
                    """
                    UPDATE agent_idempotency
                    SET status='completed', result_identity=?, updated_at_us=?
                    WHERE scope=? AND idempotency_key=? AND request_hash=?
                    """,
                    (
                        result_identity,
                        occurred_at_us,
                        scope,
                        idempotency_key,
                        expected_request_hash,
                    ),
                )
                self._audit(
                    connection,
                    category="idempotency",
                    subject_id=f"{scope}:{idempotency_key}",
                    action="completed",
                    payload={
                        "scope": scope,
                        "request_hash": expected_request_hash,
                        "result_identity": result_identity,
                    },
                    occurred_at=occurred_at,
                )
        record = self._reader.get_idempotency(scope, idempotency_key)
        if record is None:
            raise AgentPersistenceError(
                "Completed idempotency record is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return record

    def try_acquire_lease(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        owner_token: str,
        now: datetime,
        lease_until: datetime,
    ) -> LeaseFence | None:
        """Acquire an absent/expired lease and increment its durable fence."""
        return self._coordination.try_acquire_lease(
            resource_kind=resource_kind,
            resource_id=resource_id,
            owner_token=owner_token,
            now=now,
            lease_until=lease_until,
        )

    def renew_lease(
        self,
        lease: LeaseFence,
        *,
        now: datetime,
        lease_until: datetime,
    ) -> LeaseFence:
        """Renew only the exact active owner/fence/revision tuple."""
        return self._coordination.renew_lease(
            lease,
            now=now,
            lease_until=lease_until,
        )

    def release_lease(
        self,
        lease: LeaseFence,
        *,
        released_at: datetime,
    ) -> LeaseFence:
        """Expire only the exact active owner/fence/revision tuple."""
        return self._coordination.release_lease(lease, released_at=released_at)

    def set_retention(self, metadata: RetentionMetadata) -> RetentionMetadata:
        """Upsert typed retention metadata without deleting any target."""
        return self._coordination.set_retention(metadata)


__all__ = ["AgentStoreWriter"]
