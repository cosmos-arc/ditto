"""Unit tests for the strategy governance domain model and lifecycle."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    REVIEW_ONLY_DECISIONS,
    ReviewOutcome,
    StrategyActivePointer,
    StrategyDecision,
    StrategyVersion,
    StrategyVersionState,
    next_lifecycle,
    validate_reactivation_target,
)


def _version(
    *,
    strategy_id: str = "strategy-1",
    version: int = 1,
    spec_hash: str = "a" * 64,
) -> StrategyVersion:
    return StrategyVersion(
        strategy_id=strategy_id,
        version=version,
        parent_version=None,
        schema_version=GOVERNANCE_SCHEMA_VERSION,
        spec_hash=spec_hash,
        spec_json={"version": version},
        created_at="2026-07-23T00:00:00Z",
    )


def test_version_state_and_review_enums_are_explicit() -> None:
    assert set(StrategyVersionState) == {
        StrategyVersionState.DRAFT,
        StrategyVersionState.REVIEW,
        StrategyVersionState.PUBLISHED,
        StrategyVersionState.DEPRECATED,
    }
    assert set(ReviewOutcome) == {
        ReviewOutcome.PENDING,
        ReviewOutcome.APPROVED,
        ReviewOutcome.REJECTED,
    }


def test_strategy_version_is_immutable() -> None:
    version = _version()

    with pytest.raises(FrozenInstanceError):
        version.spec_hash = "0" * 64  # type: ignore[misc]


def test_next_lifecycle_submit_review_moves_draft_to_review_pending() -> None:
    state, review = next_lifecycle(
        StrategyVersionState.DRAFT,
        ReviewOutcome.PENDING,
        StrategyDecision.SUBMIT_REVIEW,
    )

    assert state is StrategyVersionState.REVIEW
    assert review is ReviewOutcome.PENDING


def test_next_lifecycle_review_decisions_set_outcome() -> None:
    approved_state, approved_review = next_lifecycle(
        StrategyVersionState.REVIEW, ReviewOutcome.PENDING, StrategyDecision.APPROVE
    )
    rejected_state, rejected_review = next_lifecycle(
        StrategyVersionState.REVIEW, ReviewOutcome.PENDING, StrategyDecision.REJECT
    )

    assert (approved_state, approved_review) == (
        StrategyVersionState.REVIEW,
        ReviewOutcome.APPROVED,
    )
    assert (rejected_state, rejected_review) == (
        StrategyVersionState.REVIEW,
        ReviewOutcome.REJECTED,
    )


def test_next_lifecycle_publish_requires_approved_review() -> None:
    state, review = next_lifecycle(
        StrategyVersionState.REVIEW, ReviewOutcome.APPROVED, StrategyDecision.PUBLISH
    )

    assert (state, review) == (StrategyVersionState.PUBLISHED, ReviewOutcome.APPROVED)


def test_next_lifecycle_publish_rejects_pending_review() -> None:
    with pytest.raises(ValueError):
        next_lifecycle(
            StrategyVersionState.REVIEW, ReviewOutcome.PENDING, StrategyDecision.PUBLISH
        )


def test_next_lifecycle_deprecates_published_version() -> None:
    state, _ = next_lifecycle(
        StrategyVersionState.PUBLISHED,
        ReviewOutcome.APPROVED,
        StrategyDecision.DEPRECATE,
    )

    assert state is StrategyVersionState.DEPRECATED


def test_next_lifecycle_rejects_unauthorized_transitions() -> None:
    """Draft cannot be published or deprecated without review approval."""

    for decision in (StrategyDecision.PUBLISH, StrategyDecision.DEPRECATE):
        with pytest.raises(ValueError):
            next_lifecycle(StrategyVersionState.DRAFT, ReviewOutcome.PENDING, decision)


def test_rejected_review_locks_version_out_of_non_review_decisions() -> None:
    """A rejected version can only be cloned; no publish/deprecate/reactivate."""

    for decision in REVIEW_ONLY_DECISIONS:
        with pytest.raises(ValueError):
            next_lifecycle(
                StrategyVersionState.REVIEW, ReviewOutcome.REJECTED, decision
            )


def test_validate_reactivation_target_accepts_published_version() -> None:
    validate_reactivation_target(
        StrategyVersionState.PUBLISHED, ReviewOutcome.APPROVED
    )  # no raise


def test_validate_reactivation_target_rejects_deprecated() -> None:
    with pytest.raises(ValueError):
        validate_reactivation_target(
            StrategyVersionState.DEPRECATED, ReviewOutcome.APPROVED
        )


def test_active_pointer_carries_revision_for_cas() -> None:
    pointer = StrategyActivePointer(
        strategy_id="strategy-1",
        active_version=3,
        pointer_revision=7,
        activation_event_id="event-1",
    )

    assert pointer.active_version == 3
    assert pointer.pointer_revision == 7
