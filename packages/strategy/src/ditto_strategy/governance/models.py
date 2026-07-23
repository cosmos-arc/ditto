"""
Immutable strategy governance version, lifecycle and active-pointer models.

Version payloads are insert-only; lifecycle is expressed through append-only
decision events and a rebuildable state projection. At most one active pointer
exists per strategy and is swapped via compare-and-swap revision.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "GOVERNANCE_SCHEMA_VERSION",
    "REVIEW_ONLY_DECISIONS",
    "ReviewOutcome",
    "StrategyActivationEvent",
    "StrategyActivePointer",
    "StrategyDecision",
    "StrategyDecisionEvent",
    "StrategyVersion",
    "StrategyVersionState",
    "StrategyVersionStateRecord",
    "next_lifecycle",
    "validate_reactivation_target",
]

GOVERNANCE_SCHEMA_VERSION = 1


class StrategyVersionState(StrEnum):
    """Lifecycle state of one immutable strategy version."""

    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ReviewOutcome(StrEnum):
    """Outcome of a review gate on one version."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class StrategyDecision(StrEnum):
    """Append-only governance decisions recorded as provenance events."""

    SUBMIT_REVIEW = "submit_review"
    APPROVE = "approve"
    REJECT = "reject"
    PUBLISH = "publish"
    DEPRECATE = "deprecate"
    REACTIVATE = "reactivate"


#: Decisions that require an approved (non-rejected) review, or that are not
#: version lifecycle transitions at all. A rejected version cannot exercise any
#: of them; it can only be cloned into a fresh draft.
REVIEW_ONLY_DECISIONS = (
    StrategyDecision.PUBLISH,
    StrategyDecision.DEPRECATE,
    StrategyDecision.REACTIVATE,
)


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    """Immutable strategy version; payload is insert-only and never updated."""

    strategy_id: str
    version: int
    parent_version: int | None
    schema_version: int
    spec_hash: str
    spec_json: Mapping[str, object]
    created_at: str


@dataclass(frozen=True, slots=True)
class StrategyVersionStateRecord:
    """Rebuildable projection of one version's lifecycle state (CAS)."""

    strategy_id: str
    version: int
    state: StrategyVersionState
    review_outcome: ReviewOutcome
    state_revision: int


@dataclass(frozen=True, slots=True)
class StrategyDecisionEvent:
    """Append-only review/publish/deprecate decision provenance."""

    event_id: str
    strategy_id: str
    version: int
    decision: StrategyDecision
    actor: str
    reason: str
    decided_at: str


@dataclass(frozen=True, slots=True)
class StrategyActivePointer:
    """One active version per strategy; pointer_revision drives CAS swaps."""

    strategy_id: str
    active_version: int
    pointer_revision: int
    activation_event_id: str


@dataclass(frozen=True, slots=True)
class StrategyActivationEvent:
    """Append-only active-pointer switch provenance."""

    event_id: str
    strategy_id: str
    target_version: int
    activation_kind: StrategyDecision
    actor: str
    reason: str
    activated_at: str


def _illegal(decision: StrategyDecision, reason: str) -> ValueError:
    return ValueError(f"{decision.value}: {reason}")


_LIFECYCLE_RULES: dict[
    StrategyDecision,
    tuple[
        StrategyVersionState,
        ReviewOutcome,
        StrategyVersionState,
        ReviewOutcome,
    ],
] = {
    StrategyDecision.SUBMIT_REVIEW: (
        StrategyVersionState.DRAFT,
        ReviewOutcome.PENDING,
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
    ),
    StrategyDecision.APPROVE: (
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        StrategyVersionState.REVIEW,
        ReviewOutcome.APPROVED,
    ),
    StrategyDecision.REJECT: (
        StrategyVersionState.REVIEW,
        ReviewOutcome.PENDING,
        StrategyVersionState.REVIEW,
        ReviewOutcome.REJECTED,
    ),
    StrategyDecision.PUBLISH: (
        StrategyVersionState.REVIEW,
        ReviewOutcome.APPROVED,
        StrategyVersionState.PUBLISHED,
        ReviewOutcome.APPROVED,
    ),
    StrategyDecision.DEPRECATE: (
        StrategyVersionState.PUBLISHED,
        ReviewOutcome.APPROVED,
        StrategyVersionState.DEPRECATED,
        ReviewOutcome.APPROVED,
    ),
}


def next_lifecycle(
    state: StrategyVersionState,
    review_outcome: ReviewOutcome,
    decision: StrategyDecision,
) -> tuple[StrategyVersionState, ReviewOutcome]:
    """
    Apply one governance decision; raise on illegal transitions.

    Reactivation is an active-pointer operation, not a version lifecycle
    transition, so it is rejected here.
    """
    rule = _LIFECYCLE_RULES.get(decision)
    if rule is None:
        raise _illegal(decision, "not a version lifecycle transition")
    required_state, required_review, new_state, new_review = rule
    if state is not required_state or review_outcome is not required_review:
        raise _illegal(
            decision,
            f"requires {required_state.value}/{required_review.value}",
        )
    return new_state, new_review


def validate_reactivation_target(
    state: StrategyVersionState,
    review_outcome: ReviewOutcome,
) -> None:
    """Ensure only a published, approved, non-deprecated version can be reactivated."""
    if (
        state is not StrategyVersionState.PUBLISHED
        or review_outcome is not ReviewOutcome.APPROVED
    ):
        raise ValueError("reactivation target must be a published approved version")
