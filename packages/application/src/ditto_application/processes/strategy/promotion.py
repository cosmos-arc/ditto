"""
Strategy promotion process: evidence-gated publish and active-pointer switch.

The process is the only writer that advances a reviewed strategy version into
production. It refuses stale evidence (bundle hash mismatch), any blocking hard
gate, or a missing holdout claim, then asks the governance service to publish
the version and switch the active pointer. The process holds no storage of its
own; it orchestrates :class:`GovernanceService` over an immutable evidence
bundle produced by the research control plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_analysis.experiments import (
    HARD_GATE_RULE_IDS,
    REVIEW_PACKET_SCHEMA_VERSION,
    ExperimentId,
    ExperimentLaunchSpec,
    GateEvaluation,
    GateLayer,
    ReviewPacket,
    encode_launch_spec,
    review_blocked_by_hard_gates,
)
from ditto_strategy.governance.models import (
    StrategyActivationEvent,
    StrategyActivePointer,
    StrategyDecisionEvent,
    StrategyVersion,
)
from ditto_strategy.governance.service import (
    GovernanceService,
    PublishReviewedActivationRequest,
)

from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    mutation_event_id,
    mutation_receipt_reason,
)

__all__ = [
    "PromotionRequest",
    "PromotionResult",
    "ReviewPacketReader",
    "StrategyPromotionProcess",
    "VerifiedPromotionTarget",
    "hard_gate_contract_blocks_promotion",
    "load_verified_promotion_target",
]


class ReviewPacketReader(Protocol):
    """Read one immutable packet and its experiment-owned launch identity."""

    def get_review_packet(self, bundle_hash: str) -> ReviewPacket | None:
        """Load one review packet or return ``None`` when it is unknown."""
        ...

    def get_launch_spec(
        self, experiment_id: ExperimentId
    ) -> ExperimentLaunchSpec | None:
        """Load the persisted launch owning the packet's experiment lineage."""
        ...


class PromotionTargetReader(Protocol):
    """Narrow governance read port needed to cross-link one target version."""

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Return one immutable governance version or ``None`` when absent."""
        ...


@dataclass(frozen=True, slots=True)
class VerifiedPromotionTarget:
    """Packet, launch, and governance version proven to name one target."""

    packet: ReviewPacket
    launch: ExperimentLaunchSpec
    version: StrategyVersion


def load_verified_promotion_target(
    *,
    strategy_id: str,
    version: int,
    bundle_hash: str,
    reader: ReviewPacketReader,
    target_reader: PromotionTargetReader,
) -> VerifiedPromotionTarget:
    """Verify packet -> persisted launch -> immutable governance target identity."""
    packet = reader.get_review_packet(bundle_hash)
    if packet is None:
        raise AppCommandError(
            f"Review packet not found for bundle hash: {bundle_hash}",
            details={
                "code": "REVIEW_PACKET_NOT_FOUND",
                "strategy_id": strategy_id,
                "version": version,
                "bundle_hash": bundle_hash,
            },
        )
    if packet.schema_version != REVIEW_PACKET_SCHEMA_VERSION:
        raise AppCommandError(
            "review packet schema is read-only and cannot be promoted",
            details={
                "code": "REVIEW_PACKET_SCHEMA_UNSUPPORTED",
                "reason": "review_packet_schema_unsupported",
                "strategy_id": strategy_id,
                "version": version,
                "schema_version": packet.schema_version,
            },
        )
    actual_bundle_hash = str(packet.bundle_hash)
    if actual_bundle_hash != bundle_hash:
        raise AppCommandError(
            "persisted review packet hash does not match the requested bundle",
            details={
                "code": "REVIEW_PACKET_TARGET_MISMATCH",
                "reason": "stale_evidence_bundle",
                "strategy_id": strategy_id,
                "version": version,
                "expected": bundle_hash,
                "actual": actual_bundle_hash,
            },
        )
    launch = reader.get_launch_spec(ExperimentId(packet.lineage.experiment_id))
    if launch is None:
        raise AppCommandError(
            "Review packet experiment lineage was not found",
            details={
                "code": "REVIEW_PACKET_EXPERIMENT_NOT_FOUND",
                "reason": "evidence_experiment_not_found",
                "strategy_id": strategy_id,
                "version": version,
                "experiment_id": packet.lineage.experiment_id,
            },
        )
    expected_strategy_version = f"{strategy_id}@{version}"
    launch_spec_hash = encode_launch_spec(launch).content_hash
    if (
        str(launch.strategy_version) != expected_strategy_version
        or launch_spec_hash != packet.spec_hash
    ):
        raise AppCommandError(
            "Review packet does not belong to the promotion target",
            details={
                "code": "REVIEW_PACKET_TARGET_MISMATCH",
                "reason": "evidence_target_mismatch",
                "strategy_id": strategy_id,
                "version": version,
                "experiment_id": packet.lineage.experiment_id,
                "launch_strategy_version": str(launch.strategy_version),
                "launch_spec_hash": str(launch_spec_hash),
                "packet_launch_spec_hash": str(packet.spec_hash),
            },
        )
    governance_version = target_reader.get_version(strategy_id, version)
    if governance_version is None:
        raise AppCommandError(
            f"Strategy version not found: {strategy_id} v{version}",
            details={
                "code": "STRATEGY_VERSION_NOT_FOUND",
                "strategy_id": strategy_id,
                "version": version,
            },
        )
    if governance_version.spec_hash != str(launch.strategy_spec_hash):
        raise AppCommandError(
            "Review packet strategy spec does not match promotion target",
            details={
                "code": "REVIEW_PACKET_TARGET_MISMATCH",
                "reason": "evidence_target_mismatch",
                "strategy_id": strategy_id,
                "version": version,
                "governance_spec_hash": governance_version.spec_hash,
                "launch_strategy_spec_hash": str(launch.strategy_spec_hash),
            },
        )
    return VerifiedPromotionTarget(
        packet=packet,
        launch=launch,
        version=governance_version,
    )


@dataclass(frozen=True, slots=True)
class PromotionRequest:
    """One promotion attempt bound to an exact, frozen evidence bundle."""

    strategy_id: str
    version: int
    packet: ReviewPacket
    actor: str
    reason: str
    decided_at: str
    expected_bundle_hash: str
    expected_strategy_spec_hash: str
    idempotency: MutationIdempotency | None = None


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Outcome of a successful promotion."""

    strategy_id: str
    version: int
    bundle_hash: str
    active_pointer: StrategyActivePointer


def hard_gate_contract_blocks_promotion(
    evaluations: tuple[GateEvaluation, ...],
) -> bool:
    """Require the canonical hard-gate sequence with no mis-layered duplicate."""
    hard_rule_ids = tuple(
        evaluation.rule_id
        for evaluation in evaluations
        if evaluation.layer is GateLayer.HARD
    )
    if hard_rule_ids != HARD_GATE_RULE_IDS:
        return True
    expected_rule_ids = frozenset(HARD_GATE_RULE_IDS)
    if any(
        evaluation.rule_id in expected_rule_ids
        and evaluation.layer is not GateLayer.HARD
        for evaluation in evaluations
    ):
        return True
    return review_blocked_by_hard_gates(evaluations)


class StrategyPromotionProcess:
    """Promote a reviewed candidate to active after evidence gating."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def get_decision_event(self, event_id: str) -> StrategyDecisionEvent | None:
        """Expose the narrow durable receipt read needed before evidence probes."""
        return self._governance.get_decision_event(event_id)

    def get_activation_event(self, event_id: str) -> StrategyActivationEvent | None:
        """Expose the paired activation receipt read for atomic replay validation."""
        return self._governance.get_activation_event(event_id)

    def get_version(self, strategy_id: str, version: int) -> StrategyVersion | None:
        """Expose the immutable target read needed by the shared verifier."""
        return self._governance.get_version(strategy_id, version)

    def promote(self, request: PromotionRequest) -> PromotionResult:
        """Validate the evidence bundle, publish, and switch the active pointer."""
        if request.packet.schema_version != REVIEW_PACKET_SCHEMA_VERSION:
            raise AppProcessError(
                "review packet schema is read-only and cannot be promoted",
                reason="review_packet_schema_unsupported",
                schema_version=request.packet.schema_version,
            )
        bundle_hash = str(request.packet.bundle_hash)
        if bundle_hash != request.expected_bundle_hash:
            raise AppProcessError(
                "evidence bundle hash mismatch",
                reason="stale_evidence_bundle",
                expected=request.expected_bundle_hash,
                actual=bundle_hash,
            )
        target = self._governance.get_version(request.strategy_id, request.version)
        if target is None:
            raise AppProcessError(
                "strategy version is not registered for promotion",
                reason="strategy_version_not_found",
                strategy_id=request.strategy_id,
                version=request.version,
            )
        if target.spec_hash != request.expected_strategy_spec_hash:
            raise AppProcessError(
                "review packet strategy spec does not match promotion target",
                reason="strategy_spec_hash_mismatch",
                strategy_id=request.strategy_id,
                version=request.version,
                expected=target.spec_hash,
                actual=request.expected_strategy_spec_hash,
            )
        if hard_gate_contract_blocks_promotion(request.packet.gate_evaluations):
            raise AppProcessError(
                "a hard gate blocks promotion",
                reason="hard_gate_blocked",
                strategy_id=request.strategy_id,
                version=request.version,
            )
        if not request.packet.holdout_claim_id:
            raise AppProcessError(
                "promotion requires a one-shot holdout claim",
                reason="holdout_missing",
                strategy_id=request.strategy_id,
                version=request.version,
            )
        publish_event_id = (
            mutation_event_id(request.idempotency)
            if request.idempotency is not None
            else f"{request.strategy_id}:{request.version}:publish:{request.decided_at}"
        )
        activate_event_id = (
            f"{mutation_event_id(request.idempotency)}:activate"
            if request.idempotency is not None
            else (
                f"{request.strategy_id}:{request.version}:activate:{request.decided_at}"
            )
        )
        reason = request.reason
        expected_pointer: StrategyActivePointer | None = None
        if request.idempotency is not None:
            current_pointer = self._governance.get_active_pointer(request.strategy_id)
            current_revision = (
                0 if current_pointer is None else current_pointer.pointer_revision
            )
            expected_pointer = StrategyActivePointer(
                strategy_id=request.strategy_id,
                active_version=request.version,
                pointer_revision=current_revision + 1,
                activation_event_id=activate_event_id,
            )
            reason = mutation_receipt_reason(
                request.idempotency,
                response={
                    "strategy_id": expected_pointer.strategy_id,
                    "active_version": expected_pointer.active_version,
                    "pointer_revision": expected_pointer.pointer_revision,
                },
                human_reason=request.reason,
            )
        pointer = self._governance.publish_reviewed_and_activate(
            PublishReviewedActivationRequest(
                strategy_id=request.strategy_id,
                version=request.version,
                publish_event_id=publish_event_id,
                activate_event_id=activate_event_id,
                actor=request.actor,
                reason=reason,
                decided_at=request.decided_at,
                expected_pointer_revision=(
                    None
                    if expected_pointer is None
                    else expected_pointer.pointer_revision - 1
                ),
            ),
        )
        if expected_pointer is not None and pointer != expected_pointer:
            raise AppProcessError(
                "promotion receipt does not match committed pointer",
                reason="idempotency_receipt_invalid",
                code="IDEMPOTENCY_RECEIPT_INVALID",
            )
        return PromotionResult(
            strategy_id=request.strategy_id,
            version=request.version,
            bundle_hash=bundle_hash,
            active_pointer=pointer,
        )
