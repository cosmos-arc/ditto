"""
SQLite append-only store for immutable strategy governance state.

Version payloads are insert-only; lifecycle is expressed through append-only
decision/activation events and rebuildable state/pointer projections advanced
via compare-and-swap revision. Nothing here mutates an existing version
payload or rewrites history.
"""

from __future__ import annotations

import sqlite3

from ditto_platform.foundation import SQLitePool, logger, traced

from ditto_strategy.governance.models import (
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecision,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.strategy_spec_store import (
    get_spec_payload,
    insert_spec_payload,
)

__all__ = ["SQLiteStrategyGovernanceStore", "StrategyGovernanceCasConflict"]


class StrategyGovernanceCasConflict(Exception):
    """Raised when a compare-and-swap update misses the expected revision."""


_CREATE_VERSION = """
CREATE TABLE IF NOT EXISTS strategy_version (
    strategy_id    TEXT NOT NULL,
    version        INT  NOT NULL,
    parent_version INT,
    schema_version INT  NOT NULL,
    spec_hash      TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (strategy_id, version)
);
"""

_CREATE_STATE = """
CREATE TABLE IF NOT EXISTS strategy_version_state (
    strategy_id    TEXT NOT NULL,
    version        INT  NOT NULL,
    state          TEXT NOT NULL,
    review_outcome TEXT NOT NULL,
    state_revision INT  NOT NULL,
    PRIMARY KEY (strategy_id, version)
);
"""

_CREATE_DECISION_EVENT = """
CREATE TABLE IF NOT EXISTS strategy_decision_event (
    event_id    TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    version     INT  NOT NULL,
    decision    TEXT NOT NULL,
    actor       TEXT NOT NULL,
    reason      TEXT NOT NULL,
    decided_at  TEXT NOT NULL
);
"""

_CREATE_ACTIVE_POINTER = """
CREATE TABLE IF NOT EXISTS strategy_active_pointer (
    strategy_id         TEXT PRIMARY KEY,
    active_version      INT  NOT NULL,
    pointer_revision    INT  NOT NULL,
    activation_event_id TEXT NOT NULL
);
"""

_CREATE_ACTIVATION_EVENT = """
CREATE TABLE IF NOT EXISTS strategy_activation_event (
    event_id        TEXT PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    target_version  INT  NOT NULL,
    activation_kind TEXT NOT NULL,
    actor           TEXT NOT NULL,
    reason          TEXT NOT NULL,
    activated_at    TEXT NOT NULL
);
"""

_INSERT_VERSION = """
INSERT INTO strategy_version (
    strategy_id, version, parent_version, schema_version, spec_hash, created_at
) VALUES (?, ?, ?, ?, ?, ?)
"""
_INSERT_STATE = """
INSERT INTO strategy_version_state (
    strategy_id, version, state, review_outcome, state_revision
) VALUES (?, ?, ?, ?, ?)
"""
_GET_VERSION = """
SELECT strategy_id, version, parent_version, schema_version, spec_hash, created_at
FROM strategy_version
WHERE strategy_id = ? AND version = ?
"""
_LIST_VERSIONS = """
SELECT strategy_id, version, parent_version, schema_version, spec_hash, created_at
FROM strategy_version
WHERE strategy_id = ?
ORDER BY version DESC
"""
_LIST_VERSIONS_BY_STATE = """
SELECT v.strategy_id, v.version, v.parent_version, v.schema_version,
       v.spec_hash, v.created_at
FROM strategy_version v
JOIN strategy_version_state s
  ON s.strategy_id = v.strategy_id AND s.version = v.version
WHERE s.state = ?
ORDER BY v.created_at DESC
"""
_GET_STATE = """
SELECT strategy_id, version, state, review_outcome, state_revision
FROM strategy_version_state
WHERE strategy_id = ? AND version = ?
"""
_GET_DECISION_EVENT = """
SELECT event_id, strategy_id, version, decision, actor, reason, decided_at
FROM strategy_decision_event
WHERE event_id = ?
"""
_INSERT_DECISION_EVENT = """
INSERT INTO strategy_decision_event (
    event_id, strategy_id, version, decision, actor, reason, decided_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""
_CAS_STATE = """
UPDATE strategy_version_state
SET state = ?, review_outcome = ?, state_revision = state_revision + 1
WHERE strategy_id = ? AND version = ? AND state_revision = ?
"""
_CAS_PUBLISH_REVIEWED_STATE = """
UPDATE strategy_version_state
SET state = ?, review_outcome = ?, state_revision = state_revision + 1
WHERE strategy_id = ? AND version = ? AND state_revision = ?
  AND state = ? AND review_outcome = ?
"""
_INSERT_ACTIVATION_EVENT = """
INSERT INTO strategy_activation_event (
    event_id, strategy_id, target_version, activation_kind, actor, reason,
    activated_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""
_INSERT_ACTIVE_POINTER = """
INSERT INTO strategy_active_pointer (
    strategy_id, active_version, pointer_revision, activation_event_id
) VALUES (?, ?, ?, ?)
"""
_CAS_ACTIVE_POINTER = """
UPDATE strategy_active_pointer
SET active_version = ?, pointer_revision = pointer_revision + 1,
    activation_event_id = ?
WHERE strategy_id = ? AND pointer_revision = ?
"""
_GET_ACTIVE_POINTER = """
SELECT strategy_id, active_version, pointer_revision, activation_event_id
FROM strategy_active_pointer
WHERE strategy_id = ?
"""
_GET_ACTIVATION_EVENT = """
SELECT event_id, strategy_id, target_version, activation_kind, actor, reason,
       activated_at
FROM strategy_activation_event
WHERE event_id = ?
"""


def _row_to_version(row: sqlite3.Row) -> StrategyVersion:
    d: dict[str, object] = dict(row)
    parent = d["parent_version"]
    return StrategyVersion(
        strategy_id=str(d["strategy_id"]),
        version=int(d["version"]),  # type: ignore[arg-type]
        parent_version=None if parent is None else int(parent),  # type: ignore[arg-type]
        schema_version=int(d["schema_version"]),  # type: ignore[arg-type]
        spec_hash=str(d["spec_hash"]),
        created_at=str(d["created_at"]),
    )


def _row_to_state(row: sqlite3.Row) -> StrategyVersionStateRecord:
    d: dict[str, object] = dict(row)
    return StrategyVersionStateRecord(
        strategy_id=str(d["strategy_id"]),
        version=int(d["version"]),  # type: ignore[arg-type]
        state=StrategyVersionState(str(d["state"])),
        review_outcome=ReviewOutcome(str(d["review_outcome"])),
        state_revision=int(d["state_revision"]),  # type: ignore[arg-type]
    )


def _row_to_pointer(row: sqlite3.Row) -> StrategyActivePointer:
    d: dict[str, object] = dict(row)
    return StrategyActivePointer(
        strategy_id=str(d["strategy_id"]),
        active_version=int(d["active_version"]),  # type: ignore[arg-type]
        pointer_revision=int(d["pointer_revision"]),  # type: ignore[arg-type]
        activation_event_id=str(d["activation_event_id"]),
    )


def _row_to_decision_event(row: sqlite3.Row) -> StrategyDecisionEvent:
    d: dict[str, object] = dict(row)
    return StrategyDecisionEvent(
        event_id=str(d["event_id"]),
        strategy_id=str(d["strategy_id"]),
        version=int(d["version"]),  # type: ignore[arg-type]
        decision=StrategyDecision(str(d["decision"])),
        actor=str(d["actor"]),
        reason=str(d["reason"]),
        decided_at=str(d["decided_at"]),
    )


def _row_to_activation_event(row: sqlite3.Row) -> StrategyActivationEvent:
    d: dict[str, object] = dict(row)
    return StrategyActivationEvent(
        event_id=str(d["event_id"]),
        strategy_id=str(d["strategy_id"]),
        target_version=int(d["target_version"]),  # type: ignore[arg-type]
        activation_kind=StrategyDecision(str(d["activation_kind"])),
        actor=str(d["actor"]),
        reason=str(d["reason"]),
        activated_at=str(d["activated_at"]),
    )


class SQLiteStrategyGovernanceStore:
    """Append-only governance store backed by the shared metadata SQLitePool."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("governance.init_schema")
    def init_schema(self) -> None:
        """Create governance tables and indexes (idempotent)."""
        conn = self._pool.get_connection()
        conn.executescript(
            _CREATE_VERSION
            + _CREATE_STATE
            + _CREATE_DECISION_EVENT
            + _CREATE_ACTIVE_POINTER
            + _CREATE_ACTIVATION_EVENT
        )
        self._pool.commit()
        logger.debug("governance schema initialized", event="governance_schema_init")

    @traced("governance.insert_version")
    def insert_version(self, version: StrategyVersion) -> None:
        """
        Insert one immutable version plus its initial draft state (atomic).

        Rejects duplicate ``(strategy_id, version)`` via primary key; payloads
        are never replaced (no ``OR REPLACE``).
        """
        conn = self._pool.get_connection()
        self._insert_version_rows(conn, version)
        self._pool.commit()
        logger.debug(
            "governance version inserted",
            event="governance_version_insert",
            strategy_id=version.strategy_id,
            version=version.version,
        )

    @traced("governance.create_draft_version")
    def create_draft_version(
        self,
        spec_record: StrategySpecRecord,
        version: StrategyVersion,
        audit_event: StrategyDecisionEvent | None = None,
    ) -> None:
        """
        Atomically persist the spec payload plus a draft governance version.

        Writes the immutable ``strategy_spec`` payload and the governance
        version + initial draft state in one transaction, so a partial write
        never leaves an orphan payload or a payload-less version. Rejects
        duplicate ``(strategy_id, version)`` via primary key.
        """
        if audit_event is not None and (
            audit_event.strategy_id != version.strategy_id
            or audit_event.version != version.version
            or audit_event.decision
            not in {
                StrategyDecision.AUDIT_CREATE_DRAFT,
                StrategyDecision.AUDIT_UPDATE_DRAFT,
            }
        ):
            raise ValueError("draft audit event must identify the created version")
        conn = self._pool.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            insert_spec_payload(conn, spec_record)
            self._insert_version_rows(conn, version)
            if audit_event is not None:
                conn.execute(
                    _INSERT_DECISION_EVENT,
                    (
                        audit_event.event_id,
                        audit_event.strategy_id,
                        audit_event.version,
                        audit_event.decision.value,
                        audit_event.actor,
                        audit_event.reason,
                        audit_event.decided_at,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.debug(
            "governance draft version created",
            event="governance_draft_created",
            strategy_id=version.strategy_id,
            version=version.version,
        )

    @staticmethod
    def _insert_version_rows(
        conn: sqlite3.Connection, version: StrategyVersion
    ) -> None:
        """Write the version + initial draft state rows without committing."""
        conn.execute(
            _INSERT_VERSION,
            (
                version.strategy_id,
                version.version,
                version.parent_version,
                version.schema_version,
                version.spec_hash,
                version.created_at,
            ),
        )
        conn.execute(
            _INSERT_STATE,
            (
                version.strategy_id,
                version.version,
                StrategyVersionState.DRAFT.value,
                ReviewOutcome.PENDING.value,
                0,
            ),
        )

    @traced("governance.get_version")
    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Return one immutable version, or ``None`` if absent."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_VERSION, (strategy_id, version)).fetchone()
        return None if row is None else _row_to_version(row)

    def get_spec_record(
        self,
        strategy_id: str,
        version: int,
    ) -> StrategySpecRecord | None:
        """Return the immutable payload cross-linked by a governance version."""
        return get_spec_payload(self._pool.get_connection(), strategy_id, version)

    @traced("governance.list_versions")
    def list_versions(self, strategy_id: str) -> tuple[StrategyVersion, ...]:
        """List every immutable version for a strategy, newest first."""
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_VERSIONS, (strategy_id,)).fetchall()
        return tuple(_row_to_version(row) for row in rows)

    @traced("governance.list_versions_by_state")
    def list_versions_by_state(
        self, state: StrategyVersionState
    ) -> tuple[StrategyVersion, ...]:
        """
        List every immutable version currently in one lifecycle state.

        Cross-strategy aggregation ordered by version creation time, newest
        first. The state projection has no timestamp of its own, so the
        immutable version's ``created_at`` drives the ordering. Used to surface
        the review queue (``state == REVIEW``) across all strategies.
        """
        conn = self._pool.get_connection()
        rows = conn.execute(_LIST_VERSIONS_BY_STATE, (state.value,)).fetchall()
        return tuple(_row_to_version(row) for row in rows)

    @traced("governance.get_state")
    def get_state(
        self, strategy_id: str, version: int
    ) -> StrategyVersionStateRecord | None:
        """Return the rebuildable lifecycle projection for one version."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_STATE, (strategy_id, version)).fetchone()
        return None if row is None else _row_to_state(row)

    @traced("governance.get_decision_event")
    def get_decision_event(self, event_id: str) -> StrategyDecisionEvent | None:
        """Return one immutable lifecycle/audit event by primary key."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_DECISION_EVENT, (event_id,)).fetchone()
        return None if row is None else _row_to_decision_event(row)

    @traced("governance.append_decision")
    def append_decision(
        self,
        event: StrategyDecisionEvent,
        new_state: StrategyVersionState,
        new_review: ReviewOutcome,
        expected_revision: int,
    ) -> StrategyVersionStateRecord:
        """
        Append one decision event and CAS-advance the state projection.

        Raises :class:`StrategyGovernanceCasConflict` when the stored
        ``state_revision`` no longer equals ``expected_revision``; the event
        insert is rolled back so history stays consistent.
        """
        conn = self._pool.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                _INSERT_DECISION_EVENT,
                (
                    event.event_id,
                    event.strategy_id,
                    event.version,
                    event.decision.value,
                    event.actor,
                    event.reason,
                    event.decided_at,
                ),
            )
            cursor = conn.execute(
                _CAS_STATE,
                (
                    new_state.value,
                    new_review.value,
                    event.strategy_id,
                    event.version,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 0:
                raise StrategyGovernanceCasConflict(
                    "state CAS missed revision "
                    + f"{expected_revision} for {event.strategy_id}/{event.version}"
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        record = self.get_state(event.strategy_id, event.version)
        if record is None:
            raise RuntimeError("governance state projection missing after CAS advance")
        return record

    @traced("governance.publish_reviewed_and_activate")
    def publish_reviewed_and_activate(
        self,
        publish_event: StrategyDecisionEvent,
        activation_event: StrategyActivationEvent,
        *,
        expected_state_revision: int,
        expected_pointer_revision: int,
    ) -> StrategyActivePointer:
        """Commit publish history, lifecycle, activation history and pointer once."""
        if (
            publish_event.decision is not StrategyDecision.PUBLISH
            or activation_event.activation_kind is not StrategyDecision.PUBLISH
            or publish_event.strategy_id != activation_event.strategy_id
            or publish_event.version != activation_event.target_version
        ):
            raise ValueError("atomic promotion events must identify one publish target")
        strategy_id = publish_event.strategy_id
        target_version = publish_event.version
        conn = self._pool.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                _INSERT_DECISION_EVENT,
                (
                    publish_event.event_id,
                    strategy_id,
                    target_version,
                    publish_event.decision.value,
                    publish_event.actor,
                    publish_event.reason,
                    publish_event.decided_at,
                ),
            )
            state_cursor = conn.execute(
                _CAS_PUBLISH_REVIEWED_STATE,
                (
                    StrategyVersionState.PUBLISHED.value,
                    ReviewOutcome.APPROVED.value,
                    strategy_id,
                    target_version,
                    expected_state_revision,
                    StrategyVersionState.REVIEW.value,
                    ReviewOutcome.APPROVED.value,
                ),
            )
            if state_cursor.rowcount == 0:
                raise StrategyGovernanceCasConflict(
                    "approved review CAS missed revision "
                    + f"{expected_state_revision} for {strategy_id}/{target_version}"
                )
            conn.execute(
                _INSERT_ACTIVATION_EVENT,
                (
                    activation_event.event_id,
                    strategy_id,
                    target_version,
                    activation_event.activation_kind.value,
                    activation_event.actor,
                    activation_event.reason,
                    activation_event.activated_at,
                ),
            )
            if expected_pointer_revision == 0:
                try:
                    conn.execute(
                        _INSERT_ACTIVE_POINTER,
                        (
                            strategy_id,
                            target_version,
                            1,
                            activation_event.event_id,
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise StrategyGovernanceCasConflict(
                        f"active pointer already exists for {strategy_id}"
                    ) from None
            else:
                pointer_cursor = conn.execute(
                    _CAS_ACTIVE_POINTER,
                    (
                        target_version,
                        activation_event.event_id,
                        strategy_id,
                        expected_pointer_revision,
                    ),
                )
                if pointer_cursor.rowcount == 0:
                    raise StrategyGovernanceCasConflict(
                        "pointer CAS missed revision "
                        + f"{expected_pointer_revision} for {strategy_id}"
                    )
            pointer_row = conn.execute(
                _GET_ACTIVE_POINTER,
                (strategy_id,),
            ).fetchone()
            if pointer_row is None:
                raise RuntimeError(
                    "governance active pointer missing during promotion transaction"
                )
            pointer = _row_to_pointer(pointer_row)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return pointer

    @traced("governance.activate")
    def activate(
        self,
        strategy_id: str,
        target_version: int,
        event: StrategyActivationEvent,
        expected_pointer_revision: int,
    ) -> StrategyActivePointer:
        """
        Append an activation event and CAS-swap the active pointer.

        ``expected_pointer_revision == 0`` inserts the first pointer; any later
        activation must supply the current revision or conflict.
        """
        conn = self._pool.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                _INSERT_ACTIVATION_EVENT,
                (
                    event.event_id,
                    event.strategy_id,
                    event.target_version,
                    event.activation_kind.value,
                    event.actor,
                    event.reason,
                    event.activated_at,
                ),
            )
            if expected_pointer_revision == 0:
                conn.execute(
                    _INSERT_ACTIVE_POINTER,
                    (strategy_id, target_version, 1, event.event_id),
                )
            else:
                cursor = conn.execute(
                    _CAS_ACTIVE_POINTER,
                    (
                        target_version,
                        event.event_id,
                        strategy_id,
                        expected_pointer_revision,
                    ),
                )
                if cursor.rowcount == 0:
                    raise StrategyGovernanceCasConflict(
                        "pointer CAS missed revision "
                        + f"{expected_pointer_revision} for {strategy_id}"
                    )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if expected_pointer_revision == 0:
                raise StrategyGovernanceCasConflict(
                    f"active pointer already exists for {strategy_id}"
                ) from exc
            raise
        except Exception:
            conn.rollback()
            raise
        pointer = self.get_active_pointer(strategy_id)
        if pointer is None:
            raise RuntimeError("governance active pointer missing after activation")
        return pointer

    @traced("governance.get_active_pointer")
    def get_active_pointer(self, strategy_id: str) -> StrategyActivePointer | None:
        """Return the single active pointer for a strategy, or ``None``."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_ACTIVE_POINTER, (strategy_id,)).fetchone()
        return None if row is None else _row_to_pointer(row)

    @traced("governance.get_activation_event")
    def get_activation_event(self, event_id: str) -> StrategyActivationEvent | None:
        """Return one immutable activation event by primary key."""
        conn = self._pool.get_connection()
        row = conn.execute(_GET_ACTIVATION_EVENT, (event_id,)).fetchone()
        return None if row is None else _row_to_activation_event(row)
