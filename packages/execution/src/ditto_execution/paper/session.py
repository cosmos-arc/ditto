"""Paper-session state, durable execution records, and persistence port."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ditto_execution.errors import ExecutionError
from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperRealityResult,
)

__all__ = [
    "InMemoryPaperSessionStore",
    "PaperExecutionRecord",
    "PaperReconciliation",
    "PaperSession",
    "PaperSessionConflictError",
    "PaperSessionMutation",
    "PaperSessionStatus",
    "PaperSessionStorePort",
]


class PaperSessionConflictError(ExecutionError):
    """A paper identity, revision, or idempotency contract conflicted."""


class PaperSessionStatus(StrEnum):
    """Durable paper-session lifecycle."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True, kw_only=True)
class PaperSession:
    """One recoverable paper session tied to one immutable PAPER account."""

    session_id: str
    account_id: str
    strategy_id: str
    trade_date: str
    status: PaperSessionStatus
    revision: int
    created_at: datetime
    updated_at: datetime
    pause_reason: str | None = None

    def __post_init__(self) -> None:
        """Validate durable identity, time, and revision fields."""
        for name, value in (
            ("session_id", self.session_id),
            ("account_id", self.account_id),
            ("strategy_id", self.strategy_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        date.fromisoformat(self.trade_date)
        if self.revision < 0:
            raise ValueError("paper session revision must be non-negative")
        for name, value in (
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")

    def start(self, *, updated_at: datetime) -> PaperSession:
        """Start a created or paused session."""
        if self.status not in {PaperSessionStatus.CREATED, PaperSessionStatus.PAUSED}:
            raise PaperSessionConflictError(
                f"paper session must be created or paused to start: {self.status.value}"
            )
        return replace(
            self,
            status=PaperSessionStatus.RUNNING,
            revision=self.revision + 1,
            updated_at=updated_at,
            pause_reason=None,
        )

    def pause(self, *, updated_at: datetime, reason: str) -> PaperSession:
        """Pause only a running session and retain the operational reason."""
        if self.status is not PaperSessionStatus.RUNNING:
            raise PaperSessionConflictError(
                f"paper session must be running to pause: {self.status.value}"
            )
        if not reason.strip():
            raise ValueError("paper pause reason must be non-empty")
        return replace(
            self,
            status=PaperSessionStatus.PAUSED,
            revision=self.revision + 1,
            updated_at=updated_at,
            pause_reason=reason,
        )


@dataclass(frozen=True, kw_only=True)
class PaperSessionMutation:
    """Stored exact command receipt for session lifecycle idempotency."""

    session_id: str
    idempotency_key: str
    action: str
    request_hash: str
    resulting_session: PaperSession


@dataclass(frozen=True, kw_only=True)
class PaperExecutionRecord:
    """Immutable outcome and replay evidence for one order operation."""

    execution_id: str
    session_id: str
    account_id: str
    idempotency_key: str
    request_hash: str
    result: PaperRealityResult
    assumption: FillAssumption
    lineage: MarketSnapshotLineage
    created_at: datetime
    ledger_event_id: str | None = None

    def with_ledger_event(self, event_id: str) -> PaperExecutionRecord:
        """Attach one exact account-ledger event identity."""
        if self.ledger_event_id is not None and self.ledger_event_id != event_id:
            raise PaperSessionConflictError("paper execution ledger event conflict")
        return replace(self, ledger_event_id=event_id)


@dataclass(frozen=True, kw_only=True)
class PaperReconciliation:
    """Signed end-of-day comparison between fills and PAPER ledger facts."""

    reconciliation_id: str
    session_id: str
    trade_date: str
    order_count: int
    fill_count: int
    ledger_fill_count: int
    balanced: bool
    checksum: str
    reconciled_at: datetime


@runtime_checkable
class PaperSessionStorePort(Protocol):
    """Persistence-neutral paper session and execution journal."""

    def create_session(
        self,
        session: PaperSession,
        mutation: PaperSessionMutation | None = None,
    ) -> PaperSession:
        """Create one session and optional initial command receipt."""
        ...

    def get_session(self, session_id: str) -> PaperSession | None:
        """Read one exact session."""
        ...

    def update_session(
        self,
        session: PaperSession,
        *,
        expected_revision: int,
        mutation: PaperSessionMutation,
    ) -> PaperSession:
        """Apply one compare-and-set lifecycle mutation."""
        ...

    def get_mutation(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperSessionMutation | None:
        """Read one exact lifecycle command receipt."""
        ...

    def append_execution(self, record: PaperExecutionRecord) -> PaperExecutionRecord:
        """Append or exactly replay one execution."""
        ...

    def get_execution(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperExecutionRecord | None:
        """Resolve an execution idempotency key."""
        ...

    def list_executions(self, session_id: str) -> tuple[PaperExecutionRecord, ...]:
        """List executions in append order."""
        ...

    def mark_execution_ledgered(
        self,
        execution_id: str,
        event_id: str,
    ) -> PaperExecutionRecord:
        """Mark one persisted execution as represented in the account ledger."""
        ...

    def append_reconciliation(
        self,
        reconciliation: PaperReconciliation,
    ) -> PaperReconciliation:
        """Append or replay one reconciliation artifact."""
        ...

    def get_reconciliation(
        self,
        reconciliation_id: str,
    ) -> PaperReconciliation | None:
        """Read one reconciliation by identity."""
        ...

    def latest_reconciliation(self, session_id: str) -> PaperReconciliation | None:
        """Return the latest reconciliation for a session."""
        ...


class InMemoryPaperSessionStore:
    """Deterministic in-memory port implementation for application tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, PaperSession] = {}
        self._mutations: dict[tuple[str, str], PaperSessionMutation] = {}
        self._executions: dict[str, PaperExecutionRecord] = {}
        self._execution_keys: dict[tuple[str, str], str] = {}
        self._reconciliations: dict[str, list[PaperReconciliation]] = {}

    def create_session(
        self,
        session: PaperSession,
        mutation: PaperSessionMutation | None = None,
    ) -> PaperSession:
        """Create one exact in-memory session."""
        existing = self._sessions.get(session.session_id)
        if existing is not None:
            if existing != session:
                raise PaperSessionConflictError("paper session identity conflict")
            return existing
        self._sessions[session.session_id] = session
        if mutation is not None:
            self._store_mutation(mutation)
        return session

    def get_session(self, session_id: str) -> PaperSession | None:
        """Read one in-memory session."""
        return self._sessions.get(session_id)

    def update_session(
        self,
        session: PaperSession,
        *,
        expected_revision: int,
        mutation: PaperSessionMutation,
    ) -> PaperSession:
        """Apply an in-memory compare-and-set mutation."""
        current = self._sessions.get(session.session_id)
        if current is None:
            raise PaperSessionConflictError("paper session not found")
        if current.revision != expected_revision:
            raise PaperSessionConflictError("paper session revision conflict")
        self._store_mutation(mutation)
        self._sessions[session.session_id] = session
        return session

    def get_mutation(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperSessionMutation | None:
        """Read an in-memory mutation receipt."""
        return self._mutations.get((session_id, idempotency_key))

    def _store_mutation(self, mutation: PaperSessionMutation) -> None:
        key = (mutation.session_id, mutation.idempotency_key)
        existing = self._mutations.get(key)
        if existing is not None and existing != mutation:
            raise PaperSessionConflictError("paper session idempotency conflict")
        self._mutations[key] = mutation

    def append_execution(self, record: PaperExecutionRecord) -> PaperExecutionRecord:
        """Append or replay an in-memory execution."""
        key = (record.session_id, record.idempotency_key)
        execution_id = self._execution_keys.get(key)
        if execution_id is not None:
            existing = self._executions[execution_id]
            if existing.request_hash != record.request_hash:
                raise PaperSessionConflictError("paper execution idempotency conflict")
            return existing
        if record.execution_id in self._executions:
            raise PaperSessionConflictError("paper execution identity conflict")
        self._executions[record.execution_id] = record
        self._execution_keys[key] = record.execution_id
        return record

    def get_execution(
        self,
        session_id: str,
        idempotency_key: str,
    ) -> PaperExecutionRecord | None:
        """Resolve an in-memory execution key."""
        execution_id = self._execution_keys.get((session_id, idempotency_key))
        return self._executions.get(execution_id) if execution_id is not None else None

    def list_executions(self, session_id: str) -> tuple[PaperExecutionRecord, ...]:
        """List in-memory executions in insertion order."""
        return tuple(
            record
            for record in self._executions.values()
            if record.session_id == session_id
        )

    def mark_execution_ledgered(
        self,
        execution_id: str,
        event_id: str,
    ) -> PaperExecutionRecord:
        """Attach an account event to an in-memory execution."""
        existing = self._executions.get(execution_id)
        if existing is None:
            raise PaperSessionConflictError("paper execution not found")
        updated = existing.with_ledger_event(event_id)
        self._executions[execution_id] = updated
        return updated

    def append_reconciliation(
        self,
        reconciliation: PaperReconciliation,
    ) -> PaperReconciliation:
        """Append or replay an in-memory reconciliation."""
        records = self._reconciliations.setdefault(reconciliation.session_id, [])
        for existing in records:
            if existing.reconciliation_id == reconciliation.reconciliation_id:
                if existing != reconciliation:
                    raise PaperSessionConflictError(
                        "paper reconciliation identity conflict"
                    )
                return existing
        records.append(reconciliation)
        return reconciliation

    def get_reconciliation(
        self,
        reconciliation_id: str,
    ) -> PaperReconciliation | None:
        """Read an in-memory reconciliation by identity."""
        for records in self._reconciliations.values():
            for record in records:
                if record.reconciliation_id == reconciliation_id:
                    return record
        return None

    def latest_reconciliation(self, session_id: str) -> PaperReconciliation | None:
        """Return the latest in-memory reconciliation."""
        records = self._reconciliations.get(session_id, [])
        return records[-1] if records else None
