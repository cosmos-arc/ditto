"""Unit tests for the application review-packet assembler."""

from __future__ import annotations

from dataclasses import replace

from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SELECTION_TRACE_KINDS,
    CandidateId,
    ConstraintOperator,
    ContentHash,
    ExperimentId,
    GateFact,
    HardGateEvidence,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    ReviewExposureWeight,
    ReviewPacket,
    ReviewSelectionExposure,
    SelectionTraceArtifactRef,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_application.processes.experiments.evidence import (
    ReviewPacketInput,
    assemble_review_packet,
)


def _objective() -> PromotionObjective:
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=CandidateId("candidate-1"),
        economic_rationale="Capture durable returns after costs.",
        trial_family=TrialFamilyDeclaration(
            "family-1",
            (
                LogicalTrialIdentity(
                    ExperimentId("experiment-1"),
                    CandidateId("candidate-1"),
                    1,
                    ContentHash("a" * 64),
                    TrialKind.CURRENT,
                ),
            ),
        ),
    )


def _hard_evidence() -> HardGateEvidence:
    satisfied = GateFact(True, "verified")
    return HardGateEvidence(
        certified_snapshot=satisfied,
        ninety_six_month=satisfied,
        pit_known_at=satisfied,
        split_purge_embargo=satisfied,
        reproduction=satisfied,
        cost_assumptions=satisfied,
        baseline_declared=satisfied,
        trial_declaration=satisfied,
        holdout_claim=satisfied,
        artifact_completeness=satisfied,
        r2_live_gate=satisfied,
    )


def _selection_trace_refs() -> tuple[SelectionTraceArtifactRef, ...]:
    return tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{index}",
            content_hash=ContentHash(f"{index}" * 64),
        )
        for index, kind in enumerate(
            REVIEW_PACKET_SELECTION_TRACE_KINDS,
            start=1,
        )
    )


def _selection_exposure() -> ReviewSelectionExposure:
    return ReviewSelectionExposure(
        applicability="APPLICABLE",
        lane="STOCK_LANE",
        industry_weights=(ReviewExposureWeight("bank", 1.0),),
        size_bucket_weights=(ReviewExposureWeight("LARGE", 1.0),),
        artifact_refs=tuple(
            ref
            for ref in _selection_trace_refs()
            if ref.artifact_kind == "fold_selection_trace_exposures_v1"
        ),
    )


def _input(**overrides: object) -> ReviewPacketInput:
    base = ReviewPacketInput(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_ids=("fold-1",),
        attempt_ids=("attempt-1",),
        spec_hash=ContentHash("a" * 64),
        resolved_spec_hash=ContentHash("b" * 64),
        parameter_hash=ContentHash("c" * 64),
        snapshot_hash=ContentHash("d" * 64),
        registry_hash=ContentHash("e" * 64),
        objective=_objective(),
        objective_payload_hash=ContentHash("f" * 64),
        hard_evidence=_hard_evidence(),
        metric_values={
            ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                ResearchMetricId.MAX_DRAWDOWN, -15.0
            ),
            ResearchMetricId.NET_RETURN: ResearchMetricValue(
                ResearchMetricId.NET_RETURN, 0.08
            ),
        },
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=ContentHash("8" * 64),
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id="claim-1",
        candidate_rationale="Captures durable net return after costs.",
        selection_trace_artifact_refs=_selection_trace_refs(),
        selection_exposure=_selection_exposure(),
    )
    return replace(base, **overrides) if overrides else base


def test_assemble_returns_packet_with_pinned_schema() -> None:
    packet = assemble_review_packet(_input())

    assert isinstance(packet, ReviewPacket)
    assert packet.schema_version == REVIEW_PACKET_SCHEMA_VERSION


def test_assemble_combines_hard_and_evidence_gates() -> None:
    packet = assemble_review_packet(_input())

    rule_ids = {evaluation.rule_id for evaluation in packet.gate_evaluations}
    assert "certified_snapshot" in rule_ids  # hard layer
    assert "objective_constraint:max_drawdown" in rule_ids  # evidence layer
    assert "primary_objective_metric" in rule_ids


def test_assemble_maps_lineage_and_hashes() -> None:
    packet = assemble_review_packet(_input())

    assert packet.lineage.experiment_id == "experiment-1"
    assert packet.lineage.candidate_id == "candidate-1"
    assert packet.lineage.fold_ids == ("fold-1",)
    assert packet.spec_hash == ContentHash("a" * 64)
    assert packet.comparison_payload_hash == ContentHash("9" * 64)
    assert packet.holdout_claim_id == "claim-1"
    assert packet.selection_trace_artifact_refs == _selection_trace_refs()
    assert packet.selection_exposure == _selection_exposure()


def test_assemble_bundle_hash_is_stable() -> None:
    assert (
        assemble_review_packet(_input()).bundle_hash
        == assemble_review_packet(_input()).bundle_hash
    )


def test_assemble_bundle_hash_reflects_hard_gate_drift() -> None:
    """A flipped hard gate must change the bundle hash (stale-evidence guard)."""

    broken = replace(_input().hard_evidence, holdout_claim=GateFact(False, "broken"))

    assert (
        assemble_review_packet(_input()).bundle_hash
        != assemble_review_packet(_input(hard_evidence=broken)).bundle_hash
    )


def test_assemble_propagates_optional_none_evidence() -> None:
    packet = assemble_review_packet(
        _input(
            comparison_payload_hash=None,
            r1_impact_payload_hash=None,
            selection_evidence_artifact_id=None,
            holdout_claim_id=None,
        )
    )

    assert packet.comparison_payload_hash is None
    assert packet.r1_impact_payload_hash is None
    assert packet.selection_evidence_artifact_id is None
    assert packet.holdout_claim_id is None
