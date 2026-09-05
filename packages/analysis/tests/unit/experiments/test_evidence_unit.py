"""Unit tests for the immutable R3 review evidence bundle."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from math import inf
from typing import cast

import pytest
from ditto_analysis.experiments import ContentHash
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SCHEMA_VERSION_V1,
    REVIEW_PACKET_SCHEMA_VERSION_V2,
    REVIEW_PACKET_SELECTION_TRACE_KINDS,
    REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
    ReviewExposureWeight,
    ReviewPacket,
    ReviewPacketLineage,
    ReviewSelectionExposure,
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
    kinds: tuple[str, ...] = REVIEW_PACKET_SELECTION_TRACE_KINDS,
) -> tuple[SelectionTraceArtifactRef, ...]:
    return tuple(
        SelectionTraceArtifactRef(
            artifact_kind=kind,
            artifact_id=f"trace-{attempt_ordinal}-{kind}",
            content_hash=ContentHash(f"{attempt_ordinal + kind_ordinal:x}" * 64),
        )
        for attempt_ordinal in range(1, attempt_count + 1)
        for kind_ordinal, kind in enumerate(
            kinds,
            start=1,
        )
    )


def _v2_packet(**overrides: object) -> ReviewPacket:
    values: dict[str, object] = {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION_V2,
        "selection_trace_artifact_refs": _trace_refs(
            kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
        ),
    }
    values.update(overrides)
    return _packet(**values)


def _selection_exposure() -> ReviewSelectionExposure:
    return ReviewSelectionExposure(
        applicability="APPLICABLE",
        lane="STOCK_LANE",
        industry_weights=(
            ReviewExposureWeight("bank", 0.6),
            ReviewExposureWeight("tech", 0.4),
        ),
        size_bucket_weights=(
            ReviewExposureWeight("SMALL", 0.2),
            ReviewExposureWeight("MID", 0.3),
            ReviewExposureWeight("LARGE", 0.5),
        ),
        artifact_refs=tuple(
            ref
            for ref in _trace_refs()
            if ref.artifact_kind == "fold_selection_trace_exposures_v1"
        ),
    )


def _v3_packet(**overrides: object) -> ReviewPacket:
    values: dict[str, object] = {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "selection_trace_artifact_refs": _trace_refs(),
        "selection_exposure": _selection_exposure(),
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
    v2_refs = _trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)
    assert restored.selection_trace_artifact_refs == v2_refs
    drifted_refs = list(v2_refs)
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
    packet = _v2_packet(
        selection_trace_artifact_refs=_trace_refs(
            attempt_count=2,
            kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
        ),
    )

    assert len(packet.selection_trace_artifact_refs) == (
        2 * len(REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)
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
        _trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)[:-1],
        tuple(reversed(_trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2))),
        (
            _trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)[0],
            *_trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)[1:-1],
            _trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2)[0],
        ),
    ],
    ids=["incomplete-block", "wrong-kind-order", "duplicate-id"],
)
def test_v2_rejects_incomplete_or_noncanonical_positive_trace_refs(
    trace_refs: tuple[SelectionTraceArtifactRef, ...],
) -> None:
    with pytest.raises(ValueError):
        _v2_packet(selection_trace_artifact_refs=trace_refs)


def test_v2_rejects_duplicate_artifact_ids_after_kind_order_is_validated() -> None:
    refs = list(_trace_refs(kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2))
    refs[1] = replace(refs[1], artifact_id=refs[0].artifact_id)
    with pytest.raises(ValueError, match="duplicate artifact ids"):
        _v2_packet(selection_trace_artifact_refs=tuple(refs))


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
        _packet(
            selection_trace_artifact_refs=_trace_refs(
                kinds=REVIEW_PACKET_SELECTION_TRACE_KINDS_V2,
            ),
        )


def test_v3_round_trip_binds_exposure_summary_and_five_kind_blocks() -> None:
    original = _v3_packet()

    restored = review_packet_from_payload(original.canonical_payload())

    assert restored == original
    assert restored.schema_version == 3
    assert restored.selection_exposure == _selection_exposure()
    assert len(restored.selection_trace_artifact_refs) == 5
    assert restored.canonical_payload()["selection_exposure"] == {
        "applicability": "APPLICABLE",
        "lane": "STOCK_LANE",
        "industry_weights": [
            {"key": "bank", "weight": 0.6},
            {"key": "tech", "weight": 0.4},
        ],
        "size_bucket_weights": [
            {"key": "SMALL", "weight": 0.2},
            {"key": "MID", "weight": 0.3},
            {"key": "LARGE", "weight": 0.5},
        ],
        "artifact_refs": [
            ref.canonical_payload() for ref in _selection_exposure().artifact_refs
        ],
    }


def test_v3_etf_exposure_is_explicit_not_applicable_without_fake_weights() -> None:
    exposure = ReviewSelectionExposure(
        applicability="NOT_APPLICABLE",
        lane="ETF_LANE",
        industry_weights=(),
        size_bucket_weights=(),
        artifact_refs=tuple(
            ref
            for ref in _trace_refs()
            if ref.artifact_kind == "fold_selection_trace_exposures_v1"
        ),
    )

    packet = _v3_packet(selection_exposure=exposure)

    assert packet.selection_exposure == exposure


def test_v3_preserves_absent_exposure_without_synthesizing_weights() -> None:
    packet = _v3_packet(selection_exposure=None)

    restored = review_packet_from_payload(packet.canonical_payload())

    assert packet.canonical_payload()["selection_exposure"] is None
    assert restored.selection_exposure is None


def test_v3_rejects_empty_applicable_exposure() -> None:
    with pytest.raises(ValueError):
        _v3_packet(
            selection_exposure=ReviewSelectionExposure(
                applicability="APPLICABLE",
                lane="STOCK_LANE",
                industry_weights=(),
                size_bucket_weights=(),
                artifact_refs=(),
            ),
        )


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("experiment_id", None),
        ("experiment_id", ""),
        ("candidate_id", 7),
        ("candidate_id", ""),
        ("fold_ids", []),
        ("fold_ids", ()),
        ("attempt_ids", []),
        ("attempt_ids", ()),
    ],
)
def test_lineage_rejects_untyped_or_empty_identity(field: str, value: object) -> None:
    values: dict[str, object] = {
        "experiment_id": "experiment-1",
        "candidate_id": "candidate-1",
        "fold_ids": ("fold-1",),
        "attempt_ids": ("attempt-1",),
    }
    values[field] = value
    with pytest.raises(ValueError):
        ReviewPacketLineage(
            experiment_id=cast("str", values["experiment_id"]),
            candidate_id=cast("str | None", values["candidate_id"]),
            fold_ids=cast("tuple[str, ...]", values["fold_ids"]),
            attempt_ids=cast("tuple[str, ...]", values["attempt_ids"]),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_kind", 1),
        ("artifact_id", None),
        ("artifact_id", " padded "),
    ],
)
def test_trace_ref_rejects_non_string_and_padded_identity(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "artifact_kind": REVIEW_PACKET_SELECTION_TRACE_KINDS[0],
        "artifact_id": "trace-1",
        "content_hash": ContentHash("a" * 64),
    }
    values[field] = value
    with pytest.raises(ValueError):
        SelectionTraceArtifactRef(
            artifact_kind=cast("str", values["artifact_kind"]),
            artifact_id=cast("str", values["artifact_id"]),
            content_hash=cast("ContentHash", values["content_hash"]),
        )


@pytest.mark.parametrize(
    ("key", "weight"),
    [
        (cast("str", None), 0.5),
        ("", 0.5),
        (" padded ", 0.5),
        ("bank", cast("float", True)),
        ("bank", cast("float", "0.5")),
        ("bank", inf),
        ("bank", -0.01),
    ],
)
def test_exposure_weight_rejects_ambiguous_keys_and_values(
    key: str,
    weight: float,
) -> None:
    with pytest.raises(ValueError):
        ReviewExposureWeight(key, weight)


def test_exposure_weight_payload_normalizes_integer_weight() -> None:
    assert ReviewExposureWeight("bank", 1).canonical_payload() == {
        "key": "bank",
        "weight": 1.0,
    }


def test_selection_exposure_rejects_invalid_lane_and_weight_collections() -> None:
    ref = _selection_exposure().artifact_refs
    invalid = [
        {
            "applicability": "APPLICABLE",
            "lane": "ETF_LANE",
            "industry_weights": (),
            "size_bucket_weights": (),
            "artifact_refs": ref,
        },
        {
            "industry_weights": [],
            "size_bucket_weights": (),
            "artifact_refs": ref,
        },
        {
            "industry_weights": (cast("ReviewExposureWeight", "bank"),),
            "size_bucket_weights": (),
            "artifact_refs": ref,
        },
        {
            "industry_weights": (
                ReviewExposureWeight("bank", 0.5),
                ReviewExposureWeight("bank", 0.5),
            ),
            "size_bucket_weights": (),
            "artifact_refs": ref,
        },
        {
            "industry_weights": (),
            "size_bucket_weights": (
                ReviewExposureWeight("LARGE", 0.5),
                ReviewExposureWeight("LARGE", 0.5),
            ),
            "artifact_refs": ref,
        },
        {
            "industry_weights": (),
            "size_bucket_weights": (),
            "artifact_refs": list(ref),
        },
        {
            "industry_weights": (),
            "size_bucket_weights": (),
            "artifact_refs": (cast("SelectionTraceArtifactRef", "trace"),),
        },
        {
            "industry_weights": (),
            "size_bucket_weights": (),
            "artifact_refs": (
                SelectionTraceArtifactRef(
                    REVIEW_PACKET_SELECTION_TRACE_KINDS[0],
                    "trace-1",
                    ContentHash("a" * 64),
                ),
            ),
        },
        {
            "industry_weights": (),
            "size_bucket_weights": (),
            "artifact_refs": (),
        },
    ]
    for overrides in invalid:
        values: dict[str, object] = {
            "applicability": "NOT_APPLICABLE",
            "lane": "ETF_LANE",
            **overrides,
        }
        with pytest.raises(ValueError):
            ReviewSelectionExposure(
                applicability=cast("str", values["applicability"]),
                lane=cast("str", values["lane"]),
                industry_weights=cast(
                    "tuple[ReviewExposureWeight, ...]",
                    values["industry_weights"],
                ),
                size_bucket_weights=cast(
                    "tuple[ReviewExposureWeight, ...]",
                    values["size_bucket_weights"],
                ),
                artifact_refs=cast(
                    "tuple[SelectionTraceArtifactRef, ...]",
                    values["artifact_refs"],
                ),
            )


def test_selection_exposure_rejects_missing_applicable_and_weighted_etf_data() -> None:
    refs = _selection_exposure().artifact_refs
    weight = (ReviewExposureWeight("bank", 1.0),)
    for industry, size in (((), weight), (weight, ())):
        with pytest.raises(ValueError):
            ReviewSelectionExposure(
                "APPLICABLE",
                "STOCK_LANE",
                industry,
                size,
                refs,
            )
    with pytest.raises(ValueError):
        ReviewSelectionExposure(
            "NOT_APPLICABLE",
            "ETF_LANE",
            weight,
            (),
            refs,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("spec_hash", "hash"),
        ("comparison_payload_hash", "hash"),
        ("r1_impact_payload_hash", "hash"),
        ("gate_evaluations", []),
        ("candidate_rationale", None),
        ("candidate_rationale", ""),
        ("selection_trace_artifact_refs", []),
        (
            "selection_trace_artifact_refs",
            (cast("SelectionTraceArtifactRef", "trace"),),
        ),
    ],
)
def test_review_packet_rejects_untyped_core_fields(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _packet(**{field: value})


def test_schema_versions_reject_fields_owned_by_later_versions() -> None:
    with pytest.raises(ValueError):
        _packet(selection_exposure=_selection_exposure())
    with pytest.raises(ValueError):
        _v2_packet(selection_exposure=_selection_exposure())
    with pytest.raises(ValueError):
        _v3_packet(selection_exposure=cast("ReviewSelectionExposure", "exposure"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fold_ids", (cast("str", 1),)),
        ("fold_ids", ("",)),
        ("fold_ids", (" padded ",)),
        ("attempt_ids", (cast("str", 1),)),
        ("attempt_ids", ("",)),
        ("attempt_ids", (" padded ",)),
    ],
)
def test_v2_rejects_invalid_fold_and_attempt_members(field: str, value: object) -> None:
    lineage = ReviewPacketLineage(
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        fold_ids=cast("tuple[str, ...]", value if field == "fold_ids" else ("fold-1",)),
        attempt_ids=cast(
            "tuple[str, ...]",
            value if field == "attempt_ids" else ("attempt-1",),
        ),
    )
    with pytest.raises(ValueError):
        _v2_packet(lineage=lineage)


def test_payload_decoder_rejects_version_owned_field_leaks() -> None:
    v1 = _packet().canonical_payload()
    v1["selection_trace_artifact_refs"] = []
    with pytest.raises(ValueError):
        review_packet_from_payload(v1)

    v2 = _v2_packet().canonical_payload()
    v2["selection_exposure"] = None
    with pytest.raises(ValueError):
        review_packet_from_payload(v2)


def test_payload_decoder_preserves_fail_closed_unknown_version_handling() -> None:
    payload = _packet().canonical_payload()
    payload["schema_version"] = REVIEW_PACKET_SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="unsupported review packet schema_version"):
        review_packet_from_payload(payload)


def test_payload_decoder_rejects_invalid_trace_ref_shapes() -> None:
    invalid_values: list[object] = [None, {}, ["trace"], [{}]]
    for value in invalid_values:
        payload = _v2_packet().canonical_payload()
        payload["selection_trace_artifact_refs"] = value
        with pytest.raises(ValueError):
            review_packet_from_payload(payload)


def test_payload_decoder_rejects_invalid_exposure_shapes() -> None:
    invalid_values: list[object] = ["exposure", {}, {"applicability": "APPLICABLE"}]
    for value in invalid_values:
        payload = _v3_packet().canonical_payload()
        payload["selection_exposure"] = value
        with pytest.raises(ValueError):
            review_packet_from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("industry_weights", None),
        ("industry_weights", ["weight"]),
        ("industry_weights", [{}]),
        ("artifact_refs", None),
        ("artifact_refs", ["ref"]),
        ("artifact_refs", [{}]),
    ],
)
def test_payload_decoder_rejects_invalid_nested_exposure_shapes(
    field: str,
    value: object,
) -> None:
    payload = _v3_packet().canonical_payload()
    exposure = cast("dict[str, object]", payload["selection_exposure"])
    exposure[field] = value
    with pytest.raises(ValueError):
        review_packet_from_payload(payload)


def test_payload_decoder_fails_closed_for_non_mapping_lineage_and_gate() -> None:
    payload = _packet().canonical_payload()
    payload["lineage"] = None
    with pytest.raises(KeyError):
        review_packet_from_payload(payload)

    payload = _packet().canonical_payload()
    payload["gate_evaluations"] = [None]
    with pytest.raises(KeyError):
        review_packet_from_payload(payload)
