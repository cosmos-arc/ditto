"""
Governance service orchestrating typed decisions over an append-only store.

The service is a thin orchestration seam: it reads the current lifecycle
projection, advances it through the pure :func:`next_lifecycle` state machine,
and persists the result via the store's compare-and-swap primitives. Promotion
evidence gating (hard gates, holdout, bundle hash) is the responsibility of the
upstream promotion process, not this service.
"""

from __future__ import annotations

from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecision,
    StrategyDecisionEvent,
    StrategyVersion,
    StrategyVersionStateRecord,
    next_lifecycle,
    validate_reactivation_target,
)
from ditto_strategy.governance.protocols import StrategyGovernanceStoreProtocol
from ditto_strategy.models import StrategySpecRecord

__all__ = ["GovernanceService", "StrategyGovernanceError"]


class StrategyGovernanceError(Exception):
    """Raised when a governance operation targets an unknown version."""


class GovernanceService:
    """Apply typed governance decisions over an append-only store."""

    def __init__(self, store: StrategyGovernanceStoreProtocol) -> None:
        self._store = store

    def create_draft(
        self,
        *,
        strategy_id: str,
        version: int,
        spec_record: StrategySpecRecord,
        created_at: str,
        schema_version: int = GOVERNANCE_SCHEMA_VERSION,
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
        self._store.create_draft_version(spec_record, gov_version)

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
        *,
        event_id: str,
        actor: str,
        reason: str,
        decided_at: str,
        kind: StrategyDecision = StrategyDecision.REACTIVATE,
    ) -> StrategyActivePointer:
        """Switch the active pointer to a published, non-deprecated version."""
        state = self._require_state(strategy_id, version)
        validate_reactivation_target(state.state, state.review_outcome)
        pointer = self._store.get_active_pointer(strategy_id)
        expected = 0 if pointer is None else pointer.pointer_revision
        event = StrategyActivationEvent(
            event_id,
            strategy_id,
            version,
            kind,
            actor,
            reason,
            decided_at,
        )
        return self._store.activate(strategy_id, version, event, expected)

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
