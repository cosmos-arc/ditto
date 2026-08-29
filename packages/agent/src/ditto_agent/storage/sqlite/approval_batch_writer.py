"""Atomic approval-batch persistence for the Agent SQLite provider."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.contracts.approval import ApprovalRequest
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.runtime.episode import episode_event_hash
from ditto_agent.runtime.state_machine import transition_run
from ditto_agent.storage.sqlite._codec import epoch_us
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    StoredAgentRun,
    StoredApproval,
    StoredRunEvent,
)


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


@dataclass(frozen=True, slots=True)
class ApprovalBatchWrite:
    """Complete atomic write intent for one interrupted approval batch."""

    requests: tuple[ApprovalRequest, ...]
    provider: str
    continuation_payload: bytes
    continuation_hash: str
    expected_run_revision: int
    expected_previous_continuation_hash: str | None
    occurred_at: datetime
    event_payload_hash: str


@dataclass(frozen=True, slots=True)
class _PreparedApprovalBatch:
    requests: tuple[ApprovalRequest, ...]
    run_id: str
    request_ids: tuple[str, ...]
    provider: str
    continuation_payload: bytes
    continuation_hash: str
    expected_run_revision: int
    expected_previous_continuation_hash: str | None
    occurred_at: datetime
    occurred_at_us: int
    event_payload_hash: str
    approval_values: tuple[tuple[object, ...], ...]


def _prepare_approval_batch(batch: ApprovalBatchWrite) -> _PreparedApprovalBatch:
    requests = batch.requests
    if not requests:
        raise ValueError("approval batch must not be empty")
    request_ids = tuple(request.request_id for request in requests)
    action_hashes = tuple(request.action_hash for request in requests)
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("approval batch request IDs must be unique")
    if len(set(action_hashes)) != len(action_hashes):
        raise ValueError("approval batch action hashes must be unique")
    run_id = requests[0].run_id
    if any(request.run_id != run_id for request in requests):
        raise ValueError("approval batch must belong to exactly one run")
    if any(not request.verify_action_hash() for request in requests):
        raise ValueError("approval batch contains an invalid action hash")
    provider = normalized_text(batch.provider, field="continuation provider")
    if not batch.continuation_payload:
        raise ValueError("continuation payload must not be empty")
    continuation_hash = sha256_hex(batch.continuation_hash, field="continuation_hash")
    if hashlib.sha256(batch.continuation_payload).hexdigest() != continuation_hash:
        raise ValueError("continuation payload hash is invalid")
    previous_hash = batch.expected_previous_continuation_hash
    if previous_hash is not None:
        previous_hash = sha256_hex(
            previous_hash,
            field="expected_previous_continuation_hash",
        )
    occurred_at_us = epoch_us(batch.occurred_at, field="approval batch occurred_at")
    approval_values = tuple(
        (
            request.request_id,
            request.run_id,
            request.action_hash,
            canonical_bytes(request.action_payload()),
            ApprovalStatus.PENDING.value,
            occurred_at_us,
            epoch_us(request.expires_at, field="approval expires_at"),
        )
        for request in requests
    )
    if any(occurred_at_us >= int(values[-1]) for values in approval_values):
        raise ValueError("approval must be requested before its expiry")
    return _PreparedApprovalBatch(
        requests=requests,
        run_id=run_id,
        request_ids=request_ids,
        provider=provider,
        continuation_payload=batch.continuation_payload,
        continuation_hash=continuation_hash,
        expected_run_revision=batch.expected_run_revision,
        expected_previous_continuation_hash=previous_hash,
        occurred_at=batch.occurred_at,
        occurred_at_us=occurred_at_us,
        event_payload_hash=sha256_hex(
            batch.event_payload_hash, field="event_payload_hash"
        ),
        approval_values=approval_values,
    )


class ApprovalBatchWriter:
    """Own atomic suspension and continuation-consumption transactions."""

    def __init__(self, database: AgentDatabase) -> None:
        self._database = database
        self._reader = AgentStoreReader(database)

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        try:
            with self._database.transaction() as connection:
                yield connection
        except AgentPersistenceError:
            raise
        except sqlite3.Error as exc:
            raise AgentPersistenceError(
                "Agent approval write failed",
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

    @staticmethod
    def _suspension_source(
        connection: sqlite3.Connection, batch: _PreparedApprovalBatch
    ) -> RunStatus:
        row = connection.execute(
            "SELECT status, revision FROM agent_runs WHERE run_id=?",
            (batch.run_id,),
        ).fetchone()
        if row is None:
            raise _conflict("Agent run does not exist", "agent_run_missing")
        if int(row["revision"]) != batch.expected_run_revision:
            raise _conflict(
                "Agent run revision has changed",
                "agent_run_revision_conflict",
            )
        source = RunStatus(str(row["status"]))
        transition_run(source, RunStatus.WAITING_APPROVAL)
        return source

    @staticmethod
    def _store_continuation(
        connection: sqlite3.Connection, batch: _PreparedApprovalBatch
    ) -> None:
        row = connection.execute(
            "SELECT payload_hash FROM agent_run_continuations WHERE run_id=?",
            (batch.run_id,),
        ).fetchone()
        previous_hash = batch.expected_previous_continuation_hash
        if previous_hash is None:
            if row is not None:
                raise _conflict(
                    "Agent run already has continuation state",
                    "agent_continuation_conflict",
                )
            connection.execute(
                """
                INSERT INTO agent_run_continuations (
                    run_id, provider, payload_json, payload_hash, updated_at_us
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    batch.run_id,
                    batch.provider,
                    batch.continuation_payload,
                    batch.continuation_hash,
                    batch.occurred_at_us,
                ),
            )
            return
        if row is None or row["payload_hash"] != previous_hash:
            raise _conflict(
                "Agent continuation state has changed",
                "agent_continuation_hash_conflict",
            )
        cursor = connection.execute(
            """
            UPDATE agent_run_continuations
            SET provider=?, payload_json=?, payload_hash=?, updated_at_us=?
            WHERE run_id=? AND payload_hash=?
            """,
            (
                batch.provider,
                batch.continuation_payload,
                batch.continuation_hash,
                batch.occurred_at_us,
                batch.run_id,
                previous_hash,
            ),
        )
        if cursor.rowcount != 1:
            raise _conflict(
                "Agent continuation update lost its hash fence",
                "agent_continuation_hash_conflict",
            )

    def _insert_approval_batch(
        self,
        connection: sqlite3.Connection,
        batch: _PreparedApprovalBatch,
    ) -> None:
        for request, values in zip(batch.requests, batch.approval_values, strict=True):
            exists = connection.execute(
                "SELECT 1 FROM agent_approvals WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if exists is not None:
                raise _conflict(
                    "Approval request identity already exists",
                    "agent_approval_conflict",
                )
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
                occurred_at=batch.occurred_at,
            )

    @staticmethod
    def _mark_waiting(
        connection: sqlite3.Connection, batch: _PreparedApprovalBatch
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE agent_runs
            SET status=?, revision=revision + 1
            WHERE run_id=? AND status=? AND revision=?
            """,
            (
                RunStatus.WAITING_APPROVAL.value,
                batch.run_id,
                RunStatus.RUNNING.value,
                batch.expected_run_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise _conflict(
                "Agent run suspension lost its revision fence",
                "agent_run_revision_conflict",
            )

    def store_approval_batch(
        self, write: ApprovalBatchWrite
    ) -> tuple[StoredApproval, ...]:
        """Atomically suspend one running run with an exact approval batch."""
        batch = _prepare_approval_batch(write)
        with self._transaction() as connection:
            source = self._suspension_source(connection, batch)
            self._store_continuation(connection, batch)
            self._insert_approval_batch(connection, batch)
            self._mark_waiting(connection, batch)
            self._audit(
                connection,
                category="continuation",
                subject_id=batch.run_id,
                action="stored",
                payload={
                    "run_id": batch.run_id,
                    "provider": batch.provider,
                    "payload_hash": batch.continuation_hash,
                    "approval_ids": batch.request_ids,
                },
                occurred_at=batch.occurred_at,
            )
            self._audit(
                connection,
                category="run",
                subject_id=batch.run_id,
                action="transitioned",
                payload={
                    "source": source,
                    "target": RunStatus.WAITING_APPROVAL,
                    "revision": batch.expected_run_revision + 1,
                },
                occurred_at=batch.occurred_at,
            )
            self._append_run_event(
                connection,
                run_id=batch.run_id,
                event_type="approval_requested",
                payload_hash=batch.event_payload_hash,
                occurred_at=batch.occurred_at,
                occurred_at_us=batch.occurred_at_us,
            )
        stored = tuple(
            self._reader.get_approval(request.request_id) for request in batch.requests
        )
        if any(item is None for item in stored):
            raise AgentPersistenceError(
                "Stored approval batch is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return tuple(item for item in stored if item is not None)

    def complete_approval_resume(
        self,
        *,
        run_id: str,
        expected_run_revision: int,
        expected_continuation_hash: str,
        occurred_at: datetime,
        event_payload_hash: str,
    ) -> StoredAgentRun:
        """Atomically complete one resumed run and consume its continuation."""
        expected_continuation_hash = sha256_hex(
            expected_continuation_hash, field="expected_continuation_hash"
        )
        event_payload_hash = sha256_hex(event_payload_hash, field="event_payload_hash")
        occurred_at_us = epoch_us(occurred_at, field="resume completed_at")
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT status, revision, started_at_us
                FROM agent_runs WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise _conflict("Agent run does not exist", "agent_run_missing")
            if int(row["revision"]) != expected_run_revision:
                raise _conflict(
                    "Agent run revision has changed",
                    "agent_run_revision_conflict",
                )
            source = RunStatus(str(row["status"]))
            transition_run(source, RunStatus.COMPLETED)
            continuation = connection.execute(
                """
                SELECT payload_hash FROM agent_run_continuations WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
            if (
                continuation is None
                or continuation["payload_hash"] != expected_continuation_hash
            ):
                raise _conflict(
                    "Agent continuation state has changed",
                    "agent_continuation_hash_conflict",
                )
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET status=?, finished_at_us=?, revision=revision + 1
                WHERE run_id=? AND status=? AND revision=?
                """,
                (
                    RunStatus.COMPLETED.value,
                    occurred_at_us,
                    run_id,
                    source.value,
                    expected_run_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "Agent run completion lost its revision fence",
                    "agent_run_revision_conflict",
                )
            connection.execute(
                """
                DELETE FROM agent_run_continuations
                WHERE run_id=? AND payload_hash=?
                """,
                (run_id, expected_continuation_hash),
            )
            self._append_run_event(
                connection,
                run_id=run_id,
                event_type="approval_resume_completed",
                payload_hash=event_payload_hash,
                occurred_at=occurred_at,
                occurred_at_us=occurred_at_us,
            )
            self._audit(
                connection,
                category="continuation",
                subject_id=run_id,
                action="consumed",
                payload={
                    "run_id": run_id,
                    "payload_hash": expected_continuation_hash,
                },
                occurred_at=occurred_at,
            )
            self._audit(
                connection,
                category="run",
                subject_id=run_id,
                action="transitioned",
                payload={
                    "source": source,
                    "target": RunStatus.COMPLETED,
                    "revision": expected_run_revision + 1,
                },
                occurred_at=occurred_at,
            )
        stored = self._reader.get_run(run_id)
        if stored is None:
            raise AgentPersistenceError(
                "Completed Agent run is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored


__all__ = ["ApprovalBatchWrite", "ApprovalBatchWriter"]
