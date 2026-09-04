"""Atomic persistence for one governed Agent run execution."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.runtime.episode import (
    AgentEpisodeManifest,
    EpisodeEventRecord,
    episode_event_hash,
)
from ditto_agent.runtime.state_machine import transition_run
from ditto_agent.storage.sqlite._codec import (
    datetime_from_epoch_us,
    epoch_us,
)
from ditto_agent.storage.sqlite.audit import append_audit_event
from ditto_agent.storage.sqlite.database import AgentDatabase
from ditto_agent.storage.sqlite.episode_store import AgentEpisodeWriter
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import StoredAgentRun, StoredRunEvent

_MIN_EXECUTION_EVENT_COUNT = 2


def _conflict(message: str, reason_code: str) -> AgentConflictError:
    return AgentConflictError(message, reason_code=reason_code)


def _audit_transition(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    source: RunStatus,
    target: RunStatus,
    revision: int,
    occurred_at: datetime,
) -> None:
    append_audit_event(
        connection,
        category="run",
        subject_id=run_id,
        action="transitioned",
        payload_hash=canonical_sha256(
            {
                "source": source,
                "target": target,
                "revision": revision,
            }
        ),
        occurred_at=occurred_at,
    )


def _append_run_event(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    event_type: str,
    payload_hash: str,
    occurred_at: datetime,
) -> StoredRunEvent:
    event_type = normalized_text(event_type, field="event_type")
    payload_hash = sha256_hex(payload_hash, field="payload_hash")
    occurred_at_us = epoch_us(occurred_at, field="event occurred_at")
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


def _transition_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    expected_revision: int,
    target: RunStatus,
    occurred_at: datetime,
    event_type: str | None = None,
    event_payload_hash: str | None = None,
) -> int:
    if (event_type is None) != (event_payload_hash is None):
        raise ValueError("event_type and event_payload_hash must be supplied together")
    occurred_at_us = epoch_us(occurred_at, field="transition occurred_at")
    row = connection.execute(
        "SELECT status, revision, started_at_us FROM agent_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise _conflict("Agent run does not exist", "agent_run_missing")
    revision = int(row["revision"])
    if revision != expected_revision:
        raise _conflict("Agent run revision has changed", "agent_run_revision_conflict")
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
    _audit_transition(
        connection,
        run_id=run_id,
        source=source,
        target=target,
        revision=expected_revision + 1,
        occurred_at=occurred_at,
    )
    if event_type is not None and event_payload_hash is not None:
        _append_run_event(
            connection,
            run_id=run_id,
            event_type=event_type,
            payload_hash=event_payload_hash,
            occurred_at=occurred_at,
        )
    return expected_revision + 1


def _durable_episode_events(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> tuple[EpisodeEventRecord, ...]:
    rows = connection.execute(
        """
        SELECT event_id, run_id, run_sequence, event_type, payload_hash,
               occurred_at_us, prev_hash, event_hash
        FROM agent_run_events
        WHERE run_id=?
        ORDER BY run_sequence
        """,
        (run_id,),
    ).fetchall()
    return tuple(
        EpisodeEventRecord(
            event_id=int(row["event_id"]),
            run_id=str(row["run_id"]),
            run_sequence=int(row["run_sequence"]),
            event_type=str(row["event_type"]),
            payload_hash=str(row["payload_hash"]),
            occurred_at=datetime_from_epoch_us(
                int(row["occurred_at_us"]),
                field="event occurred_at",
            ),
            prev_hash=None if row["prev_hash"] is None else str(row["prev_hash"]),
            event_hash=str(row["event_hash"]),
        )
        for row in rows
    )


class AgentRunExecutionWriter:
    """Own atomic state, event, and Episode writes for one execution."""

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
                "Agent run execution write failed",
                reason_code="agent_write_failed",
            ) from exc

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
        with self._transaction() as connection:
            _transition_run(
                connection,
                run_id=run_id,
                expected_revision=expected_revision,
                target=target,
                occurred_at=occurred_at,
                event_type=event_type,
                event_payload_hash=event_payload_hash,
            )
        return self._read_run(run_id, action="Transitioned")

    def append_run_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload_hash: str,
        occurred_at: datetime,
    ) -> StoredRunEvent:
        """Append one event with database-assigned global and per-run sequence."""
        with self._transaction() as connection:
            return _append_run_event(
                connection,
                run_id=run_id,
                event_type=event_type,
                payload_hash=payload_hash,
                occurred_at=occurred_at,
            )

    def commit_run_execution(
        self,
        *,
        run_id: str,
        expected_revision: int,
        target: RunStatus,
        events: tuple[EpisodeEventRecord, ...],
        episode: AgentEpisodeManifest | None,
    ) -> StoredAgentRun:
        """Atomically persist one execution lifecycle, events, and Episode."""
        if len(events) < _MIN_EXECUTION_EVENT_COUNT:
            raise ValueError("execution requires start and outcome events")
        if any(event.run_id != run_id for event in events):
            raise ValueError("execution events must belong to the run")
        if episode is not None and episode.run_id != run_id:
            raise ValueError("execution episode must belong to the run")
        with self._transaction() as connection:
            running_revision = _transition_run(
                connection,
                run_id=run_id,
                expected_revision=expected_revision,
                target=RunStatus.RUNNING,
                occurred_at=events[0].occurred_at,
                event_type=events[0].event_type,
                event_payload_hash=events[0].payload_hash,
            )
            for event in events[1:-1]:
                _append_run_event(
                    connection,
                    run_id=run_id,
                    event_type=event.event_type,
                    payload_hash=event.payload_hash,
                    occurred_at=event.occurred_at,
                )
            _transition_run(
                connection,
                run_id=run_id,
                expected_revision=running_revision,
                target=target,
                occurred_at=events[-1].occurred_at,
                event_type=events[-1].event_type,
                event_payload_hash=events[-1].payload_hash,
            )
            if episode is not None:
                AgentEpisodeWriter.put_in_transaction(
                    connection,
                    replace(
                        episode,
                        events=_durable_episode_events(connection, run_id=run_id),
                    ),
                )
        return self._read_run(run_id, action="Committed")

    def _read_run(self, run_id: str, *, action: str) -> StoredAgentRun:
        stored = self._reader.get_run(run_id)
        if stored is None:
            raise AgentPersistenceError(
                f"{action} Agent run is not readable",
                reason_code="agent_write_visibility_failed",
            )
        return stored


__all__ = ["AgentRunExecutionWriter"]
