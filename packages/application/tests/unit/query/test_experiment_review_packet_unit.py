"""Unit tests for the review packet query read model."""

from __future__ import annotations

from dataclasses import replace

from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SELECTION_TRACE_KINDS,
    ContentHash,
    GateEvaluation,
    GateLayer,
    GateOutcome,
    ReviewExposureWeight,
    ReviewPacket,
    ReviewPacketLineage,
    ReviewSelectionExposure,
    SelectionTraceArtifactRef,
)
from ditto_application.queries.experiments import (
    ExperimentReviewPacketReadModel,
    ReviewExposureWeightReadModel,
    ReviewGateOutcome,
    ReviewSelectionExposureReadModel,
    ReviewSelectionTraceRef,
    build_review_packet_read_model,
)


def _gate(
    rule_id: str = "certified_snapshot",
    layer: GateLayer = GateLayer.HARD,
    outcome: GateOutcome = GateOutcome.PASS,
) -> GateEvaluation:
    return GateEvaluation(
        rule_id=rule_id,
        layer=layer,
        outcome=outcome,
        observed="verified",
        policy={"required": True},
    )


def _packet(gate_evaluations: tuple[GateEvaluation, ...] = (_gate(),)) -> ReviewPacket:
    refs = tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{index}",
            content_hash=ContentHash(f"{index + 1}" * 64),
        )
        for index, kind in enumerate(REVIEW_PACKET_SELECTION_TRACE_KINDS)
    )
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_ids=("fold-1",),
            attempt_ids=("attempt-1",),
        ),
        spec_hash=ContentHash("a" * 64),
        resolved_spec_hash=ContentHash("b" * 64),
        parameter_hash=ContentHash("c" * 64),
        snapshot_hash=ContentHash("d" * 64),
        registry_hash=ContentHash("e" * 64),
        objective_payload_hash=ContentHash("f" * 64),
        gate_evaluations=gate_evaluations,
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id="claim-1",
        candidate_rationale="Captures durable net return after costs.",
        selection_trace_artifact_refs=refs,
        selection_exposure=ReviewSelectionExposure(
            applicability="APPLICABLE",
            lane="STOCK_LANE",
            industry_weights=(ReviewExposureWeight("bank", 1.0),),
            size_bucket_weights=(ReviewExposureWeight("LARGE", 1.0),),
            artifact_refs=(refs[-1],),
        ),
    )


def test_read_model_maps_identity_and_bundle_hash() -> None:
    read_model = build_review_packet_read_model(_packet())

    assert isinstance(read_model, ExperimentReviewPacketReadModel)
    assert read_model.experiment_id == "experiment-1"
    assert read_model.candidate_id == "candidate-1"
    assert read_model.bundle_hash == str(_packet().bundle_hash)


def test_read_model_reports_blocked_when_hard_gate_fails() -> None:
    read_model = build_review_packet_read_model(
        _packet(gate_evaluations=(_gate(outcome=GateOutcome.FAIL),))
    )

    assert read_model.hard_review_blocked is True


def test_read_model_not_blocked_when_hard_gate_passes() -> None:
    read_model = build_review_packet_read_model(
        _packet(gate_evaluations=(_gate(outcome=GateOutcome.PASS),))
    )

    assert read_model.hard_review_blocked is False


def test_read_model_ignores_evidence_layer_for_blocking() -> None:
    """Evidence-layer failures must not block review on their own."""

    read_model = build_review_packet_read_model(
        _packet(
            gate_evaluations=(
                _gate(rule_id="certified_snapshot", outcome=GateOutcome.PASS),
                _gate(
                    rule_id="objective_constraint:max_drawdown",
                    layer=GateLayer.EVIDENCE,
                    outcome=GateOutcome.FAIL,
                ),
            )
        )
    )

    assert read_model.hard_review_blocked is False


def test_read_model_exposes_every_gate_outcome() -> None:
    evaluations = (
        _gate(rule_id="certified_snapshot", outcome=GateOutcome.PASS),
        _gate(
            rule_id="primary_objective_metric",
            layer=GateLayer.EVIDENCE,
            outcome=GateOutcome.NOT_EVALUATED,
        ),
    )
    read_model = build_review_packet_read_model(_packet(gate_evaluations=evaluations))

    assert read_model.gate_outcomes == (
        ReviewGateOutcome(rule_id="certified_snapshot", layer="hard", outcome="pass"),
        ReviewGateOutcome(
            rule_id="primary_objective_metric",
            layer="evidence",
            outcome="not_evaluated",
        ),
    )


def test_read_model_exposes_reproduction_hashes_and_lineage() -> None:
    read_model = build_review_packet_read_model(_packet())

    assert read_model.schema_version == REVIEW_PACKET_SCHEMA_VERSION
    assert read_model.spec_hash == "a" * 64
    assert read_model.resolved_spec_hash == "b" * 64
    assert read_model.parameter_hash == "c" * 64
    assert read_model.snapshot_hash == "d" * 64
    assert read_model.registry_hash == "e" * 64
    assert read_model.objective_payload_hash == "f" * 64
    assert read_model.fold_ids == ("fold-1",)
    assert read_model.attempt_ids == ("attempt-1",)


def test_read_model_exposes_evidence_and_rationale() -> None:
    read_model = build_review_packet_read_model(_packet())

    assert read_model.comparison_payload_hash == "9" * 64
    assert read_model.r1_impact_payload_hash is None
    assert read_model.selection_evidence_artifact_id == "artifact-1"
    assert read_model.holdout_claim_id == "claim-1"
    assert read_model.candidate_rationale == "Captures durable net return after costs."
    assert read_model.selection_exposure == ReviewSelectionExposureReadModel(
        applicability="APPLICABLE",
        lane="STOCK_LANE",
        industry_weights=(ReviewExposureWeightReadModel("bank", 1.0),),
        size_bucket_weights=(ReviewExposureWeightReadModel("LARGE", 1.0),),
        artifact_refs=(
            ReviewSelectionTraceRef(
                artifact_kind="fold_selection_trace_exposures_v1",
                artifact_id="trace-4",
                content_hash="5" * 64,
            ),
        ),
    )


def test_read_model_exposes_selection_trace_refs() -> None:
    kinds = REVIEW_PACKET_SELECTION_TRACE_KINDS
    refs = tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{index}",
            content_hash=ContentHash("1" * 64),
        )
        for index, kind in enumerate(kinds)
    )
    packet = replace(
        _packet(),
        selection_trace_artifact_refs=refs,
        selection_exposure=ReviewSelectionExposure(
            applicability="APPLICABLE",
            lane="STOCK_LANE",
            industry_weights=(ReviewExposureWeight("bank", 1.0),),
            size_bucket_weights=(ReviewExposureWeight("LARGE", 1.0),),
            artifact_refs=(refs[-1],),
        ),
    )
    read_model = build_review_packet_read_model(packet)

    assert read_model.selection_trace_artifact_refs == tuple(
        ReviewSelectionTraceRef(
            artifact_kind=kind,
            artifact_id=f"trace-{index}",
            content_hash="1" * 64,
        )
        for index, kind in enumerate(kinds)
    )
