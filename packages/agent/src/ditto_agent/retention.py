"""Typed, content-addressed retention plans for short-lived Agent raw state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex, utc_datetime

_RAW_CONTENT_RETENTION_DAYS = 30
_RAW_CONTENT_TARGET_KIND = "run_continuation"


class RetentionPlanConflict(RuntimeError):
    """The approved plan no longer identifies the current exact raw content."""


@dataclass(frozen=True, slots=True)
class RawContentCandidate:
    """One exact, hash-fenced raw-content row eligible for deletion."""

    target_kind: str
    target_id: str
    content_hash: str
    stored_at: datetime

    def __post_init__(self) -> None:
        """Validate the closed target kind and immutable row identity."""
        if self.target_kind != _RAW_CONTENT_TARGET_KIND:
            raise ValueError("retention candidate target kind is not deletable")
        object.__setattr__(
            self,
            "target_id",
            normalized_text(self.target_id, field="retention target_id"),
        )
        object.__setattr__(
            self,
            "content_hash",
            sha256_hex(self.content_hash, field="retention content_hash"),
        )
        object.__setattr__(
            self,
            "stored_at",
            utc_datetime(self.stored_at, field="retention stored_at"),
        )


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """Auditable dry-run output whose hash confirms the exact delete set."""

    as_of: datetime
    cutoff: datetime
    candidates: tuple[RawContentCandidate, ...]
    plan_hash: str

    def __post_init__(self) -> None:
        """Reject forged hashes, widened cutoffs, and ambiguous delete sets."""
        as_of = utc_datetime(self.as_of, field="retention as_of")
        cutoff = utc_datetime(self.cutoff, field="retention cutoff")
        if cutoff != as_of - timedelta(days=_RAW_CONTENT_RETENTION_DAYS):
            raise ValueError("Agent raw-content retention is fixed at 30 days")
        if type(self.candidates) is not tuple or any(
            type(candidate) is not RawContentCandidate for candidate in self.candidates
        ):
            raise ValueError("retention candidates must be a typed tuple")
        expected_order = tuple(
            sorted(
                self.candidates,
                key=lambda candidate: (candidate.stored_at, candidate.target_id),
            )
        )
        if self.candidates != expected_order:
            raise ValueError("retention candidates must be in deterministic order")
        target_ids = tuple(candidate.target_id for candidate in self.candidates)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("retention candidates must identify unique targets")
        if any(candidate.stored_at > cutoff for candidate in self.candidates):
            raise ValueError("retention candidate is newer than the fixed cutoff")
        expected_hash = canonical_sha256(
            {
                "schema_id": "agent-raw-content-retention-plan",
                "schema_version": 1,
                "as_of": as_of,
                "cutoff": cutoff,
                "candidates": self.candidates,
            }
        )
        actual_hash = sha256_hex(self.plan_hash, field="retention plan_hash")
        if actual_hash != expected_hash:
            raise ValueError("retention plan_hash does not match its payload")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "plan_hash", actual_hash)

    @classmethod
    def create(
        cls,
        *,
        as_of: datetime,
        cutoff: datetime,
        candidates: tuple[RawContentCandidate, ...],
    ) -> RetentionPlan:
        """Create a canonical plan over an already sorted typed candidate set."""
        as_of = utc_datetime(as_of, field="retention as_of")
        cutoff = utc_datetime(cutoff, field="retention cutoff")
        payload = {
            "schema_id": "agent-raw-content-retention-plan",
            "schema_version": 1,
            "as_of": as_of,
            "cutoff": cutoff,
            "candidates": candidates,
        }
        return cls(
            as_of=as_of,
            cutoff=cutoff,
            candidates=candidates,
            plan_hash=canonical_sha256(payload),
        )


@dataclass(frozen=True, slots=True)
class RetentionExecutionResult:
    """Immutable receipt for one approved, exact cleanup transaction."""

    plan_hash: str
    approval_id: str
    deleted_target_ids: tuple[str, ...]
    audit_payload_hash: str
    executed_at: datetime


class RawContentRetentionStore(Protocol):
    """Persistence port restricted to the sole R5-deletable content kind."""

    def list_candidates(
        self,
        *,
        cutoff: datetime,
        as_of: datetime,
    ) -> tuple[RawContentCandidate, ...]:
        """Return exact eligible rows in deterministic oldest-first order."""
        ...

    def delete_candidates(
        self,
        *,
        plan: RetentionPlan,
        approval_id: str,
        executed_at: datetime,
    ) -> RetentionExecutionResult:
        """Delete only hash-fenced plan members in one audited transaction."""
        ...


class AgentRetentionService:
    """Plan first; execute only after exact hash confirmation and approval evidence."""

    def __init__(
        self,
        *,
        store: RawContentRetentionStore,
        retention_days: int = _RAW_CONTENT_RETENTION_DAYS,
    ) -> None:
        if (
            isinstance(retention_days, bool)
            or retention_days != _RAW_CONTENT_RETENTION_DAYS
        ):
            raise ValueError("Agent raw-content retention is fixed at 30 days")
        self._store = store
        self._retention_days = retention_days

    def dry_run(self, *, as_of: datetime) -> RetentionPlan:
        """Resolve an auditable plan without mutating persistence."""
        as_of = utc_datetime(as_of, field="retention as_of")
        cutoff = as_of - timedelta(days=self._retention_days)
        candidates = self._store.list_candidates(cutoff=cutoff, as_of=as_of)
        return RetentionPlan.create(
            as_of=as_of,
            cutoff=cutoff,
            candidates=candidates,
        )

    def execute(
        self,
        plan: RetentionPlan,
        *,
        expected_plan_hash: str,
        approval_id: str,
        executed_at: datetime,
    ) -> RetentionExecutionResult:
        """Execute a previously reviewed plan under two explicit fences."""
        expected = sha256_hex(
            expected_plan_hash,
            field="retention expected_plan_hash",
        )
        if expected != plan.plan_hash:
            raise RetentionPlanConflict("retention plan confirmation hash differs")
        approval_id = normalized_text(
            approval_id,
            field="retention approval_id",
            maximum=256,
        )
        executed_at = utc_datetime(executed_at, field="retention executed_at")
        if executed_at < plan.as_of:
            raise ValueError("retention execution cannot predate the plan")
        return self._store.delete_candidates(
            plan=plan,
            approval_id=approval_id,
            executed_at=executed_at,
        )


__all__ = [
    "AgentRetentionService",
    "RawContentCandidate",
    "RawContentRetentionStore",
    "RetentionExecutionResult",
    "RetentionPlan",
    "RetentionPlanConflict",
]
