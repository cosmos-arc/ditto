"""Unit tests for the immutable R3 review evidence bundle."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from ditto_analysis.experiments import ContentHash
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SCHEMA_VERSION_V1,
    REVIEW_PACKET_SELECTION_TRACE_KINDS,
    ReviewPacket,
    ReviewPacketLineage,
    SelectionTraceArtifactRef,
    review_packet_from_payload,
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
        schema_version=REVIEW_PACKET_SCHEMA_VERSION_V1,
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


def _trace_refs(
    *,
    attempt_count: int = 1,
) -> tuple[SelectionTraceArtifactRef, ...]:
    return tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{attempt_ordinal}-{kind}",
            content_hash=ContentHash(f"{attempt_ordinal + kind_ordinal:x}" * 64),
        )
        for attempt_ordinal in range(1, attempt_count + 1)
        for kind_ordinal, kind in enumerate(
            REVIEW_PACKET_SELECTION_TRACE_KINDS,
            start=1,
        )
    )


def _v2_packet(**overrides: object) -> ReviewPacket:
    values: dict[str, object] = {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "selection_trace_artifact_refs": _trace_refs(),
    }
    values.update(overrides)
    return _packet(**values)


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
    assert payload["schema_version"] == REVIEW_PACKET_SCHEMA_VERSION_V1
    assert payload["spec_hash"] == str(ContentHash("a" * 64))
    assert isinstance(payload["gate_evaluations"], list)


def test_review_packet_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError):
        _packet(schema_version=REVIEW_PACKET_SCHEMA_VERSION + 1)


def test_review_packet_rejects_unpadded_rationale() -> None:
    with pytest.raises(ValueError):
        _packet(candidate_rationale="  padded rationale  ")


def test_review_packet_round_trip_via_canonical_payload() -> None:
    """Canonical payload survives serialization and deserialization unchanged."""
    original = _packet()
    restored = review_packet_from_payload(original.canonical_payload())

    assert restored == original
    assert restored.bundle_hash == original.bundle_hash


def test_review_packet_round_trip_preserves_optional_none_fields() -> None:
    """Optional None hashes and ids round-trip as None, not strings."""
    original = _packet(
        comparison_payload_hash=None,
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id=None,
        holdout_claim_id=None,
    )
    restored = review_packet_from_payload(original.canonical_payload())

    assert restored == original
    assert restored.comparison_payload_hash is None
    assert restored.holdout_claim_id is None


def test_v1_canonical_payload_and_hash_remain_byte_contract_compatible() -> None:
    """Adding v2 support must never rewrite or re-hash persisted v1 packets."""
    packet = _packet()

    assert "selection_trace_artifact_refs" not in packet.canonical_payload()
    assert str(packet.bundle_hash) == (
        "d8191c957156f7352857b1cdf767d0c3ca4563827ca54e7940a73716f836d832"
    )


def test_v1_round_trip_remains_read_only_compatible_without_trace_refs() -> None:
    payload = _packet().canonical_payload()

    restored = review_packet_from_payload(payload)

    assert restored.schema_version == REVIEW_PACKET_SCHEMA_VERSION_V1
    assert restored.selection_trace_artifact_refs == ()
    assert restored.canonical_payload() == payload


def test_v2_round_trip_binds_positive_trace_refs_into_bundle_hash() -> None:
    original = _v2_packet()

    restored = review_packet_from_payload(original.canonical_payload())

    assert restored == original
    assert restored.selection_trace_artifact_refs == _trace_refs()
    drifted_refs = list(_trace_refs())
    drifted_refs[0] = replace(
        drifted_refs[0],
        content_hash=ContentHash("0" * 64),
    )
    assert (
        _v2_packet(selection_trace_artifact_refs=tuple(drifted_refs)).bundle_hash
        != original.bundle_hash
    )


def test_v2_allows_trace_blocks_for_complete_family_beyond_selected_lineage() -> None:
    """The packet lineage is selected-only; trace refs cover every source row."""
    packet = _v2_packet(selection_trace_artifact_refs=_trace_refs(attempt_count=2))

    assert len(packet.selection_trace_artifact_refs) == (
        2 * len(REVIEW_PACKET_SELECTION_TRACE_KINDS)
    )


def test_v2_allows_zero_positive_refs_when_completeness_gate_records_missing() -> None:
    """Missing facts stay absent; the hard gate records absence without fake refs."""
    packet = _v2_packet(selection_trace_artifact_refs=())

    restored = review_packet_from_payload(packet.canonical_payload())

    assert packet.canonical_payload()["selection_trace_artifact_refs"] == []
    assert restored.selection_trace_artifact_refs == ()
    assert restored == packet


@pytest.mark.parametrize(
    "trace_refs",
    [
        _trace_refs()[:-1],
        tuple(reversed(_trace_refs())),
        (_trace_refs()[0], *_trace_refs()[1:-1], _trace_refs()[0]),
    ],
    ids=["incomplete-block", "wrong-kind-order", "duplicate-id"],
)
def test_v2_rejects_incomplete_or_noncanonical_positive_trace_refs(
    trace_refs: tuple[SelectionTraceArtifactRef, ...],
) -> None:
    with pytest.raises(ValueError):
        _v2_packet(selection_trace_artifact_refs=trace_refs)


def test_v2_rejects_fold_attempt_lineage_count_drift() -> None:
    with pytest.raises(ValueError):
        _v2_packet(
            lineage=ReviewPacketLineage(
                experiment_id="experiment-1",
                candidate_id="candidate-1",
                fold_ids=("fold-1", "fold-2"),
                attempt_ids=("attempt-1",),
            ),
        )


def test_v1_rejects_v2_trace_refs() -> None:
    with pytest.raises(ValueError):
        _packet(selection_trace_artifact_refs=_trace_refs())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_kind", "not-a-trace-kind"),
        ("artifact_id", ""),
        ("content_hash", "not-a-content-hash"),
    ],
)
def test_trace_ref_rejects_untyped_or_blank_identity(
    field: str,
    value: object,
) -> None:
    base: dict[str, object] = {
        "artifact_kind": REVIEW_PACKET_SELECTION_TRACE_KINDS[0],
        "artifact_id": "trace-1",
        "content_hash": ContentHash("a" * 64),
    }
    base[field] = value

    with pytest.raises(ValueError):
        SelectionTraceArtifactRef(**base)  # type: ignore[arg-type]
