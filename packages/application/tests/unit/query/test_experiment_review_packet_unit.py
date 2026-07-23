"""Unit tests for the review packet query read model."""

from __future__ import annotations

from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ContentHash,
    GateEvaluation,
    GateLayer,
    GateOutcome,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_application.queries.experiments import (
    ExperimentReviewPacketReadModel,
    ReviewGateOutcome,
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
