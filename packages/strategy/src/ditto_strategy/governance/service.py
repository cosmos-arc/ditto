"""
Governance service orchestrating typed decisions over an append-only store.

The service is a thin orchestration seam: it reads the current lifecycle
projection, advances it through the pure :func:`next_lifecycle` state machine,
and persists the result via the store's compare-and-swap primitives. Promotion
evidence gating (hard gates, holdout, bundle hash) is the responsibility of the
upstream promotion process, not this service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    ReviewOutcome,
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecision,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionState,
    StrategyVersionStateRecord,
    next_lifecycle,
    validate_reactivation_target,
)
from ditto_strategy.governance.protocols import StrategyGovernanceStoreProtocol
from ditto_strategy.models import StrategySpecRecord

__all__ = [
    "GovernanceService",
    "PublishReviewedActivationRequest",
    "StrategyGovernanceError",
]


class StrategyGovernanceError(Exception):
    """Raised when a governance operation targets an unknown version."""


def _next_event_time(value: str) -> str:
    """Advance one explicit aware timestamp for a multi-transaction seed path."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("governance event timestamp must be timezone-aware")
    return (
        (parsed.astimezone(UTC) + timedelta(microseconds=1))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class PublishReviewedActivationRequest:
    """One atomic approved-review publication and pointer activation."""

    strategy_id: str
    version: int
    publish_event_id: str
    activate_event_id: str
    actor: str
    reason: str
    decided_at: str
    expected_pointer_revision: int | None = None


class GovernanceService:
    """Apply typed governance decisions over an append-only store."""

    def __init__(self, store: StrategyGovernanceStoreProtocol) -> None:
        self._store = store

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Return the immutable version identity used by evidence binding."""
        return self._store.get_version(strategy_id, version)

    def get_spec_record(
        self,
        strategy_id: str,
        version: int,
    ) -> StrategySpecRecord | None:
        """Return the immutable payload bound to one governance version."""
        return self._store.get_spec_record(strategy_id, version)

    def create_draft(
        self,
        *,
        strategy_id: str,
        version: int,
        spec_record: StrategySpecRecord,
        created_at: str,
        schema_version: int = GOVERNANCE_SCHEMA_VERSION,
        audit_event: StrategyDecisionEvent | None = None,
    ) -> None:
        """
        Create a draft version: persist spec payload + governance version.

        The spec payload and governance version are written atomically; the
        version starts ``draft``/``pending`` and must be reviewed before
        publish. ``spec_record.spec_hash`` is reused as the governance version
        hash so payload and version stay content-addressed together.
        """
        gov_version = StrategyVersion(
            strategy_id=strategy_id,
            version=version,
            parent_version=spec_record.parent_version,
            schema_version=schema_version,
            spec_hash=spec_record.spec_hash,
            created_at=created_at,
        )
        self._store.create_draft_version(spec_record, gov_version, audit_event)

    def get_decision_event(self, event_id: str) -> StrategyDecisionEvent | None:
        """Return one immutable lifecycle/audit event by id."""
        return self._store.get_decision_event(event_id)

    def get_activation_event(self, event_id: str) -> StrategyActivationEvent | None:
        """Return one immutable activation event by id."""
        return self._store.get_activation_event(event_id)

    def get_active_pointer(self, strategy_id: str) -> StrategyActivePointer | None:
        """Return the current active pointer."""
        return self._store.get_active_pointer(strategy_id)

    def submit_review(
        self,
        strategy_id: str,
        version: int,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        """Move a draft version into review (outcome ``pending``)."""
        return self._apply(
            strategy_id,
            version,
            StrategyDecision.SUBMIT_REVIEW,
            event_id=event_id,
            actor=actor,
            reason=reason,
            decided_at=decided_at,
        )

    def approve(
        self,
        strategy_id: str,
        version: int,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        """Approve a pending review."""
        return self._apply(
            strategy_id,
            version,
            StrategyDecision.APPROVE,
            event_id=event_id,
            actor=actor,
            reason=reason,
            decided_at=decided_at,
        )

    def reject(
        self,
        strategy_id: str,
        version: int,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        """Reject a pending review (the version can then only be cloned)."""
        return self._apply(
            strategy_id,
            version,
            StrategyDecision.REJECT,
            event_id=event_id,
            actor=actor,
            reason=reason,
            decided_at=decided_at,
        )

    def publish(
        self,
        strategy_id: str,
        version: int,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        """Publish an approved review (lifecycle state only; pointer is separate)."""
        return self._apply(
            strategy_id,
            version,
            StrategyDecision.PUBLISH,
            event_id=event_id,
            actor=actor,
            reason=reason,
            decided_at=decided_at,
        )

    def publish_reviewed_and_activate(
        self,
        request: PublishReviewedActivationRequest,
    ) -> StrategyActivePointer:
        """Atomically publish one approved review and advance the active pointer."""
        state = self._require_state(request.strategy_id, request.version)
        next_state, next_review = next_lifecycle(
            state.state,
            state.review_outcome,
            StrategyDecision.PUBLISH,
        )
        if (
            next_state is not StrategyVersionState.PUBLISHED
            or next_review is not ReviewOutcome.APPROVED
        ):
            raise ValueError("publish transition did not resolve to approved/published")
        expected_pointer_revision = request.expected_pointer_revision
        if expected_pointer_revision is None:
            pointer = self._store.get_active_pointer(request.strategy_id)
            expected_pointer_revision = (
                0 if pointer is None else pointer.pointer_revision
            )
        publish_event = StrategyDecisionEvent(
            request.publish_event_id,
            request.strategy_id,
            request.version,
            StrategyDecision.PUBLISH,
            request.actor,
            request.reason,
            request.decided_at,
        )
        activation_event = StrategyActivationEvent(
            request.activate_event_id,
            request.strategy_id,
            request.version,
            StrategyDecision.PUBLISH,
            request.actor,
            request.reason,
            request.decided_at,
        )
        return self._store.publish_reviewed_and_activate(
            publish_event,
            activation_event,
            expected_state_revision=state.state_revision,
            expected_pointer_revision=expected_pointer_revision,
        )

    def deprecate(
        self,
        strategy_id: str,
        version: int,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        """Deprecate a published version (it can no longer be activated)."""
        return self._apply(
            strategy_id,
            version,
            StrategyDecision.DEPRECATE,
            event_id=event_id,
            actor=actor,
            reason=reason,
            decided_at=decided_at,
        )

    def activate(
        self,
        strategy_id: str,
        version: int,
        event: StrategyActivationEvent,
        *,
        expected_pointer_revision: int | None = None,
    ) -> StrategyActivePointer:
        """
        Switch the active pointer to a published, non-deprecated version.

        When ``expected_pointer_revision`` is supplied it is used as the
        compare-and-swap guard verbatim, letting a caller hold an optimistic
        lock over the pointer it last read. When it is ``None`` the service
        reads the current revision, preserving the legacy seed/system path.
        """
        if event.strategy_id != strategy_id or event.target_version != version:
            raise ValueError(
                "activation event target does not match the requested strategy version"
            )
        state = self._require_state(strategy_id, version)
        validate_reactivation_target(state.state, state.review_outcome)
        if expected_pointer_revision is None:
            pointer = self._store.get_active_pointer(strategy_id)
            expected = 0 if pointer is None else pointer.pointer_revision
        else:
            expected = expected_pointer_revision
        return self._store.activate(strategy_id, version, event, expected)

    def publish_and_activate(
        self,
        *,
        strategy_id: str,
        version: int,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyActivePointer:
        """
        Advance a draft to published and activate it (seed/system fast-path).

        Walks the full lifecycle submit→approve→publish then activates the
        pointer. Idempotent: a version already active is a no-op; a published
        version is only (re-)activated. Deprecated versions cannot be revived.
        """
        state = self._require_state(strategy_id, version)
        if state.state is StrategyVersionState.DEPRECATED:
            raise StrategyGovernanceError(
                f"cannot revive deprecated version: {strategy_id}/{version}"
            )
        prefix = f"{strategy_id}:{version}"
        event_time = decided_at
        if state.state is StrategyVersionState.DRAFT:
            state = self.submit_review(
                strategy_id,
                version,
                event_id=f"{prefix}:submit_review:{event_time}",
                actor=actor,
                reason=reason,
                decided_at=event_time,
            )
            event_time = _next_event_time(event_time)
        if state.review_outcome is ReviewOutcome.PENDING:
            state = self.approve(
                strategy_id,
                version,
                event_id=f"{prefix}:approve:{event_time}",
                actor=actor,
                reason=reason,
                decided_at=event_time,
            )
            event_time = _next_event_time(event_time)
        if state.state is StrategyVersionState.REVIEW:
            self.publish(
                strategy_id,
                version,
                event_id=f"{prefix}:publish:{event_time}",
                actor=actor,
                reason=reason,
                decided_at=event_time,
            )
            event_time = _next_event_time(event_time)
        pointer = self._store.get_active_pointer(strategy_id)
        if pointer is not None and pointer.active_version == version:
            return pointer
        activate_event = StrategyActivationEvent(
            f"{prefix}:activate:{event_time}",
            strategy_id,
            version,
            StrategyDecision.PUBLISH,
            actor,
            reason,
            event_time,
        )
        return self.activate(strategy_id, version, activate_event)

    def _apply(
        self,
        strategy_id: str,
        version: int,
        decision: StrategyDecision,
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
    ) -> StrategyVersionStateRecord:
        state = self._require_state(strategy_id, version)
        new_state, new_review = next_lifecycle(
            state.state, state.review_outcome, decision
        )
        event = StrategyDecisionEvent(
            event_id, strategy_id, version, decision, actor, reason, decided_at
        )
        return self._store.append_decision(
            event, new_state, new_review, state.state_revision
        )

    def _require_state(
        self, strategy_id: str, version: int
    ) -> StrategyVersionStateRecord:
        state = self._store.get_state(strategy_id, version)
        if state is None:
            raise StrategyGovernanceError(
                f"governance version not found: {strategy_id}/{version}"
            )
        return state
