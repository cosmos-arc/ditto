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

Evidence-gated publish runs through :class:`StrategyPromotionProcess` once a
review packet is available (see :class:`PublishStrategyVersionHandler`); the
seed/system fast-path lives in ``commands.strategy.PublishStrategyHandler``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import orjson
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

from ditto_application.commands.strategy_governance_receipts import (
    invalid_strategy_receipt,
    pointer_receipt,
    replay_strategy_activation,
    replay_strategy_decision,
    replay_strategy_publish,
    state_receipt,
)
from ditto_application.contracts import (
    StrategyActivePointerInfo,
    StrategyVersionStateInfo,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    mutation_event_id,
    mutation_receipt_reason,
)
from ditto_application.processes.strategy.promotion import (
    PromotionRequest,
    ReviewPacketReader,
    StrategyPromotionProcess,
    hard_gate_contract_blocks_promotion,
    load_verified_promotion_target,
)

__all__ = [
    "ApproveReviewCommand",
    "ApproveReviewHandler",
    "DeprecateStrategyCommand",
    "DeprecateStrategyHandler",
    "PublishStrategyVersionCommand",
    "PublishStrategyVersionHandler",
    "ReactivateStrategyCommand",
    "ReactivateStrategyHandler",
    "RejectReviewCommand",
    "RejectReviewHandler",
    "ReviewPacketReader",
    "SubmitReviewCommand",
    "SubmitReviewHandler",
    "reactivate_confirmation_phrase",
]

_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
#: Governance failures mapped at this boundary into one typed AppCommandError.
_GOVERNANCE_FAILURES = (
    sqlite3.IntegrityError,
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


def reactivate_confirmation_phrase(
    strategy_id: str,
    version: int,
    expected_pointer_revision: int,
) -> str:
    """Return the exact operator phrase bound to one target and pointer read."""
    return (
        f"strategy:reactivate:{strategy_id}@{version}:"
        f"pointer-revision:{expected_pointer_revision}:confirm"
    )


def _required_reactivation_text(
    value: str,
    *,
    field_name: str,
    strategy_id: str,
    version: int,
) -> str:
    """Normalize one required human-authored field before any governance write."""
    normalized = value.strip()
    if normalized:
        return normalized
    raise AppCommandError(
        f"Strategy reactivation {field_name} must not be blank",
        details={
            "code": "STRATEGY_REACTIVATION_INPUT_INVALID",
            "reason": f"{field_name}_blank",
            "strategy_id": strategy_id,
            "version": version,
        },
    )


def _reactivation_audit_reason(reason: str, impact_summary: str) -> str:
    """Encode the complete human rationale using the canonical JSON convention."""
    return orjson.dumps(
        {
            "reason": reason,
            "impact_summary": impact_summary,
        },
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")


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
    bundle_hash: str
    actor: str
    reason: str
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class ApproveReviewCommand:
    """Approve one pending review."""

    strategy_id: str
    version: int
    actor: str
    reason: str
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class RejectReviewCommand:
    """Reject one pending review (the version can then only be cloned)."""

    strategy_id: str
    version: int
    actor: str
    reason: str
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class DeprecateStrategyCommand:
    """Deprecate one published version so it can no longer be activated."""

    strategy_id: str
    version: int
    actor: str
    reason: str
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class ReactivateStrategyCommand:
    """Switch the active pointer back to a published version (optimistic CAS)."""

    strategy_id: str
    version: int
    actor: str
    reason: str
    confirmation: str
    impact_summary: str
    expected_pointer_revision: int
    idempotency: MutationIdempotency | None = None


class SubmitReviewHandler:
    """Submit one draft version for review."""

    def __init__(
        self,
        governance: GovernanceService,
        reader: ReviewPacketReader,
    ) -> None:
        self._governance = governance
        self._reader = reader

    def handle(self, command: SubmitReviewCommand) -> StrategyVersionStateInfo:
        """Forward the submit-review decision with minted provenance."""
        replay = replay_strategy_decision(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        target = load_verified_promotion_target(
            strategy_id=command.strategy_id,
            version=command.version,
            bundle_hash=command.bundle_hash,
            reader=self._reader,
            target_reader=self._governance,
        )
        if hard_gate_contract_blocks_promotion(target.packet.gate_evaluations):
            raise AppCommandError(
                "a hard gate blocks review submission",
                details={
                    "code": "HARD_GATE_FAILED",
                    "reason": "hard_gate_blocked",
                    "strategy_id": command.strategy_id,
                    "version": command.version,
                },
            )
        decided_at = _utc_now_iso()
        expected = StrategyVersionStateInfo(
            command.strategy_id, command.version, "review", "pending"
        )
        reason = command.reason
        if command.idempotency is not None:
            reason = mutation_receipt_reason(
                command.idempotency,
                response=state_receipt(expected),
                human_reason=command.reason,
            )
        try:
            record = self._governance.submit_review(
                command.strategy_id,
                command.version,
                event_id=(
                    mutation_event_id(command.idempotency)
                    if command.idempotency is not None
                    else _event_id(
                        command.strategy_id,
                        command.version,
                        "submit_review",
                        decided_at,
                    )
                ),
                actor=command.actor,
                reason=reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            replay = replay_strategy_decision(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        result = _to_state_info(record)
        if command.idempotency is not None and result != expected:
            raise invalid_strategy_receipt()
        return result


class ApproveReviewHandler:
    """Approve one pending review."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: ApproveReviewCommand) -> StrategyVersionStateInfo:
        """Forward the approval decision with minted provenance."""
        replay = replay_strategy_decision(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        decided_at = _utc_now_iso()
        expected = StrategyVersionStateInfo(
            command.strategy_id, command.version, "review", "approved"
        )
        reason = command.reason
        if command.idempotency is not None:
            reason = mutation_receipt_reason(
                command.idempotency,
                response=state_receipt(expected),
                human_reason=command.reason,
            )
        try:
            record = self._governance.approve(
                command.strategy_id,
                command.version,
                event_id=(
                    mutation_event_id(command.idempotency)
                    if command.idempotency is not None
                    else _event_id(
                        command.strategy_id, command.version, "approve", decided_at
                    )
                ),
                actor=command.actor,
                reason=reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            replay = replay_strategy_decision(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        result = _to_state_info(record)
        if command.idempotency is not None and result != expected:
            raise invalid_strategy_receipt()
        return result


class RejectReviewHandler:
    """Reject one pending review."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: RejectReviewCommand) -> StrategyVersionStateInfo:
        """Forward the rejection decision with minted provenance."""
        replay = replay_strategy_decision(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        decided_at = _utc_now_iso()
        expected = StrategyVersionStateInfo(
            command.strategy_id, command.version, "review", "rejected"
        )
        reason = command.reason
        if command.idempotency is not None:
            reason = mutation_receipt_reason(
                command.idempotency,
                response=state_receipt(expected),
                human_reason=command.reason,
            )
        try:
            record = self._governance.reject(
                command.strategy_id,
                command.version,
                event_id=(
                    mutation_event_id(command.idempotency)
                    if command.idempotency is not None
                    else _event_id(
                        command.strategy_id, command.version, "reject", decided_at
                    )
                ),
                actor=command.actor,
                reason=reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            replay = replay_strategy_decision(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        result = _to_state_info(record)
        if command.idempotency is not None and result != expected:
            raise invalid_strategy_receipt()
        return result


class DeprecateStrategyHandler:
    """Deprecate one published version."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: DeprecateStrategyCommand) -> StrategyVersionStateInfo:
        """Forward the deprecation decision with minted provenance."""
        replay = replay_strategy_decision(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        decided_at = _utc_now_iso()
        expected = StrategyVersionStateInfo(
            command.strategy_id, command.version, "deprecated", "approved"
        )
        reason = command.reason
        if command.idempotency is not None:
            reason = mutation_receipt_reason(
                command.idempotency,
                response=state_receipt(expected),
                human_reason=command.reason,
            )
        try:
            record = self._governance.deprecate(
                command.strategy_id,
                command.version,
                event_id=(
                    mutation_event_id(command.idempotency)
                    if command.idempotency is not None
                    else _event_id(
                        command.strategy_id, command.version, "deprecate", decided_at
                    )
                ),
                actor=command.actor,
                reason=reason,
                decided_at=decided_at,
            )
        except _GOVERNANCE_FAILURES as exc:
            replay = replay_strategy_decision(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        result = _to_state_info(record)
        if command.idempotency is not None and result != expected:
            raise invalid_strategy_receipt()
        return result


class ReactivateStrategyHandler:
    """Switch the active pointer back to a published version."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def handle(self, command: ReactivateStrategyCommand) -> StrategyActivePointerInfo:
        """Forward the optimistic-pointer CAS decision with typed error mapping."""
        replay = replay_strategy_activation(
            self._governance,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        reason = _required_reactivation_text(
            command.reason,
            field_name="reason",
            strategy_id=command.strategy_id,
            version=command.version,
        )
        impact_summary = _required_reactivation_text(
            command.impact_summary,
            field_name="impact_summary",
            strategy_id=command.strategy_id,
            version=command.version,
        )
        expected_confirmation = reactivate_confirmation_phrase(
            command.strategy_id,
            command.version,
            command.expected_pointer_revision,
        )
        if command.confirmation != expected_confirmation:
            raise AppCommandError(
                "Strategy reactivation confirmation does not match target",
                details={
                    "code": "STRATEGY_REACTIVATION_CONFIRMATION_MISMATCH",
                    "reason": "confirmation_mismatch",
                    "strategy_id": command.strategy_id,
                    "version": command.version,
                    "expected_confirmation": expected_confirmation,
                },
            )
        decided_at = _utc_now_iso()
        expected = StrategyActivePointerInfo(
            strategy_id=command.strategy_id,
            active_version=command.version,
            pointer_revision=command.expected_pointer_revision + 1,
        )
        audit_reason = _reactivation_audit_reason(reason, impact_summary)
        if command.idempotency is not None:
            audit_reason = mutation_receipt_reason(
                command.idempotency,
                response=pointer_receipt(expected),
                human_reason=audit_reason,
            )
        event = StrategyActivationEvent(
            (
                mutation_event_id(command.idempotency)
                if command.idempotency is not None
                else _event_id(
                    command.strategy_id, command.version, "reactivate", decided_at
                )
            ),
            command.strategy_id,
            command.version,
            StrategyDecision.REACTIVATE,
            command.actor,
            audit_reason,
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
            replay = replay_strategy_activation(
                self._governance,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id, command.version, exc
            ) from exc
        result = _to_pointer_info(pointer)
        if command.idempotency is not None and result != expected:
            raise invalid_strategy_receipt()
        return result


@dataclass(frozen=True, slots=True)
class PublishStrategyVersionCommand:
    """Promote one reviewed version using a frozen evidence bundle hash."""

    strategy_id: str
    version: int
    bundle_hash: str
    actor: str
    reason: str
    idempotency: MutationIdempotency | None = None


class PublishStrategyVersionHandler:
    """Promote a reviewed version after evidence-gated validation."""

    def __init__(
        self,
        process: StrategyPromotionProcess,
        reader: ReviewPacketReader,
    ) -> None:
        self._process = process
        self._reader = reader

    def handle(
        self, command: PublishStrategyVersionCommand
    ) -> StrategyActivePointerInfo:
        """Load the packet, run evidence gates, and switch the active pointer."""
        replay = replay_strategy_publish(
            self._process,
            command.idempotency,
            strategy_id=command.strategy_id,
            version=command.version,
        )
        if replay is not None:
            return replay
        target = load_verified_promotion_target(
            strategy_id=command.strategy_id,
            version=command.version,
            bundle_hash=command.bundle_hash,
            reader=self._reader,
            target_reader=self._process,
        )
        decided_at = _utc_now_iso()
        request = PromotionRequest(
            strategy_id=command.strategy_id,
            version=command.version,
            packet=target.packet,
            actor=command.actor,
            reason=command.reason,
            decided_at=decided_at,
            expected_bundle_hash=command.bundle_hash,
            expected_strategy_spec_hash=str(target.launch.strategy_spec_hash),
            idempotency=command.idempotency,
        )
        try:
            result = self._process.promote(request)
        except AppProcessError as exc:
            replay = replay_strategy_publish(
                self._process,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            details = dict(exc.details)
            details.update(
                {"strategy_id": command.strategy_id, "version": command.version}
            )
            raise AppCommandError(str(exc), details=details) from exc
        except _GOVERNANCE_FAILURES as exc:
            replay = replay_strategy_publish(
                self._process,
                command.idempotency,
                strategy_id=command.strategy_id,
                version=command.version,
            )
            if replay is not None:
                return replay
            raise _map_governance_error(
                command.strategy_id,
                command.version,
                exc,
            ) from exc
        return _to_pointer_info(result.active_pointer)
