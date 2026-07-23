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

from ditto_analysis.experiments import ReviewPacket, review_blocked_by_hard_gates
from ditto_strategy.governance.models import StrategyActivePointer, StrategyDecision
from ditto_strategy.governance.service import GovernanceService

from ditto_application.exceptions import AppProcessError

__all__ = ["PromotionRequest", "PromotionResult", "StrategyPromotionProcess"]


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


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Outcome of a successful promotion."""

    strategy_id: str
    version: int
    bundle_hash: str
    active_pointer: StrategyActivePointer


class StrategyPromotionProcess:
    """Promote a reviewed candidate to active after evidence gating."""

    def __init__(self, governance: GovernanceService) -> None:
        self._governance = governance

    def promote(self, request: PromotionRequest) -> PromotionResult:
        """Validate the evidence bundle, publish, and switch the active pointer."""
        bundle_hash = str(request.packet.bundle_hash)
        if bundle_hash != request.expected_bundle_hash:
            raise AppProcessError(
                "evidence bundle hash mismatch",
                reason="stale_evidence_bundle",
                expected=request.expected_bundle_hash,
                actual=bundle_hash,
            )
        if review_blocked_by_hard_gates(request.packet.gate_evaluations):
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
            f"{request.strategy_id}:{request.version}:publish:{request.decided_at}"
        )
        self._governance.publish(
            request.strategy_id,
            request.version,
            event_id=publish_event_id,
            actor=request.actor,
            reason=request.reason,
            decided_at=request.decided_at,
        )
        activate_event_id = (
            f"{request.strategy_id}:{request.version}:activate:{request.decided_at}"
        )
        pointer = self._governance.activate(
            request.strategy_id,
            request.version,
            event_id=activate_event_id,
            actor=request.actor,
            reason=request.reason,
            decided_at=request.decided_at,
            kind=StrategyDecision.PUBLISH,
        )
        return PromotionResult(
            strategy_id=request.strategy_id,
            version=request.version,
            bundle_hash=bundle_hash,
            active_pointer=pointer,
        )
