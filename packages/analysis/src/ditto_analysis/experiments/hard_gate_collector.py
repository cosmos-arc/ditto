"""
Project typed observed facts onto the eleven hard-correctness gate facts.

This module is a pure research-plane projection: :func:`collect_hard_gate_evidence`
reads only :class:`HardGateEvidenceView` and assembles a fully populated
:class:`HardGateEvidence`. It performs no I/O and imports no store, artifact, or
production-package type. Downstream code (for example an evidence collector in
the application layer) is responsible for assembling the view from a snapshot
manifest, artifact listing, and trial declaration before invoking the projection.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_analysis.experiments.gates import GateFact, HardGateEvidence
from ditto_analysis.experiments.models import ContentHash

__all__ = [
    "HardGateEvidenceView",
    "collect_hard_gate_evidence",
]

#: Minimum walk-forward out-of-sample span (design section 9.1).
_REQUIRED_OOS_MONTHS = 96

#: Only point-in-time policy that satisfies the ``pit_known_at`` gate.
_PIT_POLICY_SAMPLE_TIME = "sample_time"


@dataclass(frozen=True, slots=True)
class HardGateEvidenceView:
    """
    Typed observed facts projected onto the eleven hard-correctness gates.

    Every field is an analysis-owned primitive or value object so the view can
    be assembled without leaking store, artifact, or production-package types
    across the analysis boundary. ``r2_live_gate`` has no field here because its
    outcome is pinned to ``NOT_EVALUATED`` during the Beta stage (it is closed
    only by G2 live acceptance, which is out of scope for this projection).
    """

    certified_snapshot: bool
    snapshot_id: str
    oos_month_count: int
    pit_policy: str
    purge_embargo_configured: bool
    reproduction_fingerprints: tuple[ContentHash, ...]
    cost_config_hash: ContentHash
    baseline_candidate_id: str
    trial_count: int
    expected_trial_count: int
    holdout_claim_id: str | None
    artifact_complete: bool
    artifact_missing: tuple[str, ...]


def collect_hard_gate_evidence(view: HardGateEvidenceView) -> HardGateEvidence:
    """
    Project typed observed facts onto the eleven hard-correctness gate facts.

    The projection is total and side-effect free. ``r2_live_gate`` is pinned to
    ``satisfied=None`` because live-acceptance closure is deferred to the G2
    stage; every other gate derives its satisfaction from the corresponding
    view field. The returned :class:`HardGateEvidence` is ready to be fed to
    :func:`evaluate_hard_gates` for outcome projection.
    """
    return HardGateEvidence(
        certified_snapshot=GateFact(
            view.certified_snapshot,
            {"snapshot_id": view.snapshot_id},
        ),
        ninety_six_month=GateFact(
            view.oos_month_count >= _REQUIRED_OOS_MONTHS,
            {
                "oos_months": view.oos_month_count,
                "required": _REQUIRED_OOS_MONTHS,
            },
        ),
        pit_known_at=GateFact(
            view.pit_policy == _PIT_POLICY_SAMPLE_TIME,
            {"pit_policy": view.pit_policy},
        ),
        split_purge_embargo=GateFact(
            view.purge_embargo_configured,
            None,
        ),
        reproduction=GateFact(
            len(view.reproduction_fingerprints) > 0,
            None,
        ),
        cost_assumptions=GateFact(
            # V1 (design section 6): a present cost-config hash satisfies the
            # gate. V2 will compare two hashes for cross-candidate consistency.
            True,
            {"cost_config_hash": str(view.cost_config_hash)},
        ),
        baseline_declared=GateFact(
            bool(view.baseline_candidate_id),
            {"baseline_candidate_id": view.baseline_candidate_id},
        ),
        trial_declaration=GateFact(
            view.trial_count == view.expected_trial_count,
            {
                "trial_count": view.trial_count,
                "expected": view.expected_trial_count,
            },
        ),
        holdout_claim=GateFact(
            None if view.holdout_claim_id is None else True,
            {"claim_id": view.holdout_claim_id},
        ),
        artifact_completeness=GateFact(
            view.artifact_complete,
            {"missing": view.artifact_missing},
        ),
        r2_live_gate=GateFact(None),
    )
