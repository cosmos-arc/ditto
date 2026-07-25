"""
Strategy governance command boundary — typed state-machine decisions.

Each handler mints a stable event id and UTC timestamp, forwards one typed
governance decision (submit-review / approve / reject / deprecate / reactivate),
maps the three governance failure modes — unknown version
(:class:`StrategyGovernanceError`), compare-and-swap conflict
(:class:`StrategyGovernanceCasConflict`) and illegal lifecycle transition
(``ValueError``) — into a single typed :class:`AppCommandError` whose message
carries the keyword the API error mapper keys off (``not found`` / ``conflict``
/ ``transition``), and returns an application-owned read model so capability
types never leak past this boundary.

Evidence-gated publish is intentionally not exposed here: the promotion path
runs through :class:`StrategyPromotionProcess` once a review packet is
available, and the seed/system fast-path lives in
``commands.strategy.PublishStrategyHandler``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_strategy.governance.models import (
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecision,
    StrategyVersionStateRecord,
)
from ditto_strategy.governance.service import (
    GovernanceService,
    StrategyGovernanceError,
)
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    StrategyGovernanceCasConflict,
)

from ditto_application.contracts import (
    StrategyActivePointerInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError

__all__ = [
    "ApproveReviewCommand",
    "ApproveReviewHandler",
    "DeprecateStrategyCommand",
    "DeprecateStrategyHandler",
    "ReactivateStrategyCommand",
    "ReactivateStrategyHandler",
    "RejectReviewCommand",
    "RejectReviewHandler",
    "SubmitReviewCommand",
    "SubmitReviewHandler",
]

_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
#: Governance failures mapped at this boundary into one typed AppCommandError.
_GOVERNANCE_FAILURES = (
    StrategyGovernanceError,
    StrategyGovernanceCasConflict,
    ValueError,
)


def _utc_now_iso() -> str:
    """Stable ISO-8601 UTC timestamp for governance decision provenance."""
    return datetime.now(UTC).strftime(_UTC_FMT)


def _event_id(strategy_id: str, version: int, decision: str, decided_at: str) -> str:
    """Deterministic event id provenance for one governance decision."""
    return f"{strategy_id}:{version}:{decision}:{decided_at}"


def _map_governance_error(
    strategy_id: str, version: int, exc: Exception
) -> AppCommandError:
    """Translate one governance failure into a typed command boundary error."""
    details: dict[str, object] = {"strategy_id": strategy_id, "version": version}
    if isinstance(exc, StrategyGovernanceError):
        return AppCommandError(
            f"Strategy version not found: {strategy_id} v{version}",
            details={**details, "code": "STRATEGY_VERSION_NOT_FOUND"},
        )
    if isinstance(exc, StrategyGovernanceCasConflict):
        return AppCommandError(
            f"Strategy revision conflict for {strategy_id} v{version}: {exc}",
            details={**details, "code": "STRATEGY_REVISION_CONFLICT"},
        )
    if isinstance(exc, ValueError):
        return AppCommandError(
            f"Invalid governance transition for {strategy_id} v{version}: {exc}",
            details={**details, "code": "STRATEGY_INVALID_TRANSITION"},
        )
    return AppCommandError(
        f"Strategy governance error for {strategy_id} v{version}: {exc}",
        details={**details, "code": "STRATEGY_GOVERNANCE_ERROR"},
    )


def _to_state_info(record: StrategyVersionStateRecord) -> StrategyVersionStateInfo:
    """Project one governance state record into an application read model."""
    return StrategyVersionStateInfo(
        strategy_id=record.strategy_id,
        version=record.version,
        state=str(record.state),
        review_outcome=str(record.review_outcome),
    )


def _to_pointer_info(pointer: StrategyActivePointer) -> StrategyActivePointerInfo:
    """Project one active pointer into an application read model."""
    return StrategyActivePointerInfo(
        strategy_id=pointer.strategy_id,
        active_version=pointer.active_version,
        pointer_revision=pointer.pointer_revision,
    )


@dataclass(frozen=True, slots=True)
class SubmitReviewCommand:
    """Move one draft version into review."""

    strategy_id: str
    version: int
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class ApproveReviewCommand:
    """Approve one pending review."""

    strategy_id: str
    version: int
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class RejectReviewCommand:
    """Reject one pending review (the version can then only be cloned)."""

    strategy_id: str
    version: int
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class DeprecateStrategyCommand:
    """Deprecate one published version so it can no longer be activated."""

    strategy_id: str
    version: int
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReactivateStrategyCommand:
    """Switch the active pointer back to a published version (optimistic CAS)."""

    strategy_id: str
    version: int
    actor: str
    reason: str
    expected_pointer_revision: int


class SubmitReviewHandler:
    """Submit one draft version for review."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: SubmitReviewCommand) -> StrategyVersionStateInfo:
        """Forward the submit-review decision with minted provenance."""
        decided_at = _utc_now_iso()
        try:
            record = self._governance.submit_review(
                command.strategy_id,
                command.version,
                event_id=_event_id(
                    command.strategy_id, command.version, "submit_review", decided_at
                ),
                actor=command.actor,
                reason=command.reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        return _to_state_info(record)


class ApproveReviewHandler:
    """Approve one pending review."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: ApproveReviewCommand) -> StrategyVersionStateInfo:
        """Forward the approval decision with minted provenance."""
        decided_at = _utc_now_iso()
        try:
            record = self._governance.approve(
                command.strategy_id,
                command.version,
                event_id=_event_id(
                    command.strategy_id, command.version, "approve", decided_at
                ),
                actor=command.actor,
                reason=command.reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        return _to_state_info(record)


class RejectReviewHandler:
    """Reject one pending review."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: RejectReviewCommand) -> StrategyVersionStateInfo:
        """Forward the rejection decision with minted provenance."""
        decided_at = _utc_now_iso()
        try:
            record = self._governance.reject(
                command.strategy_id,
                command.version,
                event_id=_event_id(
                    command.strategy_id, command.version, "reject", decided_at
                ),
                actor=command.actor,
                reason=command.reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        return _to_state_info(record)


class DeprecateStrategyHandler:
    """Deprecate one published version."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: DeprecateStrategyCommand) -> StrategyVersionStateInfo:
        """Forward the deprecation decision with minted provenance."""
        decided_at = _utc_now_iso()
        try:
            record = self._governance.deprecate(
                command.strategy_id,
                command.version,
                event_id=_event_id(
                    command.strategy_id, command.version, "deprecate", decided_at
                ),
                actor=command.actor,
                reason=command.reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        return _to_state_info(record)


class ReactivateStrategyHandler:
    """Switch the active pointer back to a published version."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: ReactivateStrategyCommand) -> StrategyActivePointerInfo:
        """Forward the optimistic-pointer CAS decision with typed error mapping."""
        decided_at = _utc_now_iso()
        event = StrategyActivationEvent(
            _event_id(command.strategy_id, command.version, "reactivate", decided_at),
            command.strategy_id,
            command.version,
            StrategyDecision.REACTIVATE,
            command.actor,
            command.reason,
            decided_at,
        )
        try:
            pointer = self._governance.activate(
                command.strategy_id,
                command.version,
                event,
                expected_pointer_revision=command.expected_pointer_revision,
            )
        except _GOVERNANCE_FAILURES as exc:
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        return _to_pointer_info(pointer)
