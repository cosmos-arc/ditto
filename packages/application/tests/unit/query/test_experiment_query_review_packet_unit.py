"""Tests for ExperimentQueryFacade.get_review_packet — review packet wiring.

The facade loads the content-addressed packet by experiment lineage identity
via the analysis reader and delegates projection to
:func:`build_review_packet_read_model`. These tests cover the wiring (reader
call, None pass-through) — the projection itself is covered by
``test_experiment_review_packet_unit.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SELECTION_TRACE_KINDS,
    ContentHash,
    ExperimentId,
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
    ExperimentQueryFacade,
    ExperimentReviewPacketReadModel,
)


def _packet() -> ReviewPacket:
    refs = tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{index}",
            content_hash=ContentHash(f"{index}" * 64),
        )
        for index, kind in enumerate(REVIEW_PACKET_SELECTION_TRACE_KINDS, start=1)
    )
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id="exp-1",
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
        gate_evaluations=(
            GateEvaluation(
                rule_id="certified_snapshot",
                layer=GateLayer.HARD,
                outcome=GateOutcome.PASS,
                observed="verified",
                policy={"required": True},
            ),
        ),
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id=None,
        holdout_claim_id=None,
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


def test_get_review_packet_returns_read_model() -> None:
    reader = MagicMock()
    reader.get_review_packet_for_experiment.return_value = _packet()
    facade = ExperimentQueryFacade(reader=reader)

    result = facade.get_review_packet("exp-1")

    assert isinstance(result, ExperimentReviewPacketReadModel)
    assert result.experiment_id == "exp-1"
    assert result.bundle_hash == str(_packet().bundle_hash)
    reader.get_review_packet_for_experiment.assert_called_once_with(
        ExperimentId("exp-1")
    )


def test_get_review_packet_returns_none_when_absent() -> None:
    reader = MagicMock()
    reader.get_review_packet_for_experiment.return_value = None
    facade = ExperimentQueryFacade(reader=reader)

    assert facade.get_review_packet("exp-1") is None
