"""Unit tests for the immutable R3 review evidence bundle."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from ditto_analysis.experiments import ContentHash
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_analysis.experiments.gates import (
    GateEvaluation,
    GateLayer,
    GateOutcome,
)


def _gate(
    rule_id: str = "certified_snapshot",
    outcome: GateOutcome = GateOutcome.PASS,
) -> GateEvaluation:
    return GateEvaluation(
        rule_id=rule_id,
        layer=GateLayer.HARD,
        outcome=outcome,
        observed="verified",
        policy={"required": True},
    )


def _packet(**overrides: object) -> ReviewPacket:
    base = ReviewPacket(
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
        gate_evaluations=(_gate(),),
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=ContentHash("8" * 64),
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id="claim-1",
        candidate_rationale="Captures durable net return after costs.",
    )
    return replace(base, **overrides) if overrides else base


def test_review_packet_is_immutable() -> None:
    packet = _packet()

    with pytest.raises(FrozenInstanceError):
        packet.candidate_rationale = "tampered"  # type: ignore[misc]


def test_bundle_hash_is_stable_for_identical_packets() -> None:
    assert _packet().bundle_hash == _packet().bundle_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spec_hash", ContentHash("0" * 64)),
        ("resolved_spec_hash", ContentHash("0" * 64)),
        ("parameter_hash", ContentHash("0" * 64)),
        ("snapshot_hash", ContentHash("0" * 64)),
        ("registry_hash", ContentHash("0" * 64)),
        ("objective_payload_hash", ContentHash("0" * 64)),
        ("comparison_payload_hash", ContentHash("0" * 64)),
        ("r1_impact_payload_hash", None),
        ("selection_evidence_artifact_id", "artifact-other"),
        ("holdout_claim_id", None),
        ("candidate_rationale", "A different economic rationale."),
    ],
)
def test_bundle_hash_detects_stale_evidence(field: str, value: object) -> None:
    """promotion relies on this hash to refuse stale bundles."""

    assert _packet(**{field: value}).bundle_hash != _packet().bundle_hash


def test_bundle_hash_detects_gate_outcome_drift() -> None:
    """A gate flipping from pass to fail must invalidate the bundle hash."""

    passed = _packet(gate_evaluations=(_gate(outcome=GateOutcome.PASS),))
    failed = _packet(gate_evaluations=(_gate(outcome=GateOutcome.FAIL),))

    assert passed.bundle_hash != failed.bundle_hash


def test_bundle_hash_detects_lineage_drift() -> None:
    original = _packet()
    drifted = _packet(
        lineage=ReviewPacketLineage(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_ids=("fold-1", "fold-2"),
            attempt_ids=("attempt-1",),
        ),
    )

    assert original.bundle_hash != drifted.bundle_hash


def test_canonical_payload_is_a_json_ready_mapping() -> None:
    payload = _packet().canonical_payload()

    assert isinstance(payload, dict)
    assert payload["schema_version"] == REVIEW_PACKET_SCHEMA_VERSION
    assert payload["spec_hash"] == str(ContentHash("a" * 64))
    assert isinstance(payload["gate_evaluations"], list)


def test_review_packet_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError):
        _packet(schema_version=REVIEW_PACKET_SCHEMA_VERSION + 1)


def test_review_packet_rejects_unpadded_rationale() -> None:
    with pytest.raises(ValueError):
        _packet(candidate_rationale="  padded rationale  ")
