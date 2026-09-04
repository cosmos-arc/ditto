"""Adversarial validation tests for walk-forward diagnostic evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from ditto_analysis.experiments import ContentHash, FoldId
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.comparison import EvidenceStatus
from ditto_application.processes.experiments.walk_forward import (
    FoldStabilityEvidence,
    WalkForwardDiagnosticEvidence,
)

pytestmark = [pytest.mark.unit, pytest.mark.pit]

_FOLD_ONE = FoldId("wf-1")
_FOLD_TWO = FoldId("wf-2")
_HASH_ONE = ContentHash("1" * 64)
_HASH_TWO = ContentHash("2" * 64)


def _expect_invalid(reason: str, factory: Callable[[], object]) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()
    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


def test_diagnostic_rejects_status_fold_shape_and_duplicate_fold_identity() -> None:
    _expect_invalid(
        "invalid_diagnostic_status",
        lambda: WalkForwardDiagnosticEvidence(
            status=cast("EvidenceStatus", "evaluated"),
            fold_values=(),
            reason="invalid",
        ),
    )
    _expect_invalid(
        "invalid_fold_diagnostic_values",
        lambda: WalkForwardDiagnosticEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_values=cast("tuple[tuple[FoldId, object], ...]", (("wf-1", 1.0),)),
            reason="invalid",
        ),
    )
    _expect_invalid(
        "duplicate_fold_diagnostic_values",
        lambda: WalkForwardDiagnosticEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_values=((_FOLD_ONE, 1.0), (_FOLD_ONE, 2.0)),
            reason="duplicate",
        ),
    )


def test_diagnostic_status_requires_complete_values_reason_and_lineage() -> None:
    _expect_invalid(
        "invalid_evaluated_walk_forward_diagnostic",
        lambda: WalkForwardDiagnosticEvidence(
            status=EvidenceStatus.EVALUATED,
            fold_values=((_FOLD_ONE, 1.0),),
            reason=None,
            evidence_refs=("artifact://wf-1",),
            evidence_hashes=(_HASH_ONE,),
        ),
    )
    _expect_invalid(
        "not_evaluated_diagnostic_reason_required",
        lambda: WalkForwardDiagnosticEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_values=(),
            reason=None,
        ),
    )
    _expect_invalid(
        "evaluated_evidence_source_required",
        lambda: WalkForwardDiagnosticEvidence(
            status=EvidenceStatus.EVALUATED,
            fold_values=((_FOLD_ONE, 1.0), (_FOLD_TWO, 2.0)),
            reason=None,
        ),
    )


def test_diagnostic_lineage_requires_ordered_typed_unique_pairs() -> None:
    cases: tuple[
        tuple[tuple[str, ...], tuple[ContentHash, ...]],
        ...,
    ] = (
        (cast("tuple[str, ...]", "artifact://wf-1"), (_HASH_ONE,)),
        (("artifact://wf-1",), cast("tuple[ContentHash, ...]", "hash")),
        (("artifact://wf-1",), (cast("ContentHash", "1" * 64),)),
        (
            ("artifact://wf-1", "artifact://wf-1"),
            (_HASH_ONE, _HASH_TWO),
        ),
        (("artifact://wf-1",), ()),
    )

    for refs, hashes in cases:
        _expect_invalid(
            "invalid_diagnostic_evidence_identity",
            lambda refs=refs, hashes=hashes: WalkForwardDiagnosticEvidence(
                status=EvidenceStatus.NOT_EVALUATED,
                fold_values=(),
                reason="not_evaluated",
                evidence_refs=refs,
                evidence_hashes=hashes,
            ),
        )


def test_fold_stability_rejects_nonfinite_untyped_and_invalid_counts() -> None:
    _expect_invalid(
        "non_finite_walk_forward_value",
        lambda: FoldStabilityEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_returns=((_FOLD_ONE, float("nan")),),
            direction_consistent=None,
            positive_fold_count=0,
            negative_fold_count=0,
            zero_fold_count=0,
            return_range=None,
            reason="not_evaluated",
        ),
    )
    _expect_invalid(
        "invalid_fold_stability_identity",
        lambda: FoldStabilityEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_returns=((cast("FoldId", "wf-1"), 1.0),),
            direction_consistent=None,
            positive_fold_count=0,
            negative_fold_count=0,
            zero_fold_count=0,
            return_range=None,
            reason="not_evaluated",
        ),
    )
    _expect_invalid(
        "invalid_fold_direction_counts",
        lambda: FoldStabilityEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_returns=(),
            direction_consistent=None,
            positive_fold_count=-1,
            negative_fold_count=0,
            zero_fold_count=0,
            return_range=None,
            reason="not_evaluated",
        ),
    )


def test_fold_stability_status_requires_complete_or_empty_evidence() -> None:
    _expect_invalid(
        "invalid_evaluated_fold_stability",
        lambda: FoldStabilityEvidence(
            status=EvidenceStatus.EVALUATED,
            fold_returns=((_FOLD_ONE, 1.0),),
            direction_consistent=True,
            positive_fold_count=1,
            negative_fold_count=0,
            zero_fold_count=0,
            return_range=0.0,
            reason=None,
        ),
    )
    _expect_invalid(
        "invalid_not_evaluated_fold_stability",
        lambda: FoldStabilityEvidence(
            status=EvidenceStatus.NOT_EVALUATED,
            fold_returns=(),
            direction_consistent=False,
            positive_fold_count=0,
            negative_fold_count=0,
            zero_fold_count=0,
            return_range=None,
            reason="not_evaluated",
        ),
    )


def test_valid_diagnostic_payload_deep_freezes_nested_values() -> None:
    evidence = WalkForwardDiagnosticEvidence(
        status=EvidenceStatus.EVALUATED,
        fold_values=(
            (_FOLD_ONE, {"scores": [1.0, 2.0]}),
            (_FOLD_TWO, {"scores": [3.0, 4.0]}),
        ),
        reason=None,
        evidence_refs=("artifact://wf-1", "artifact://wf-2"),
        evidence_hashes=(_HASH_ONE, _HASH_TWO),
    )

    assert evidence.canonical_payload()["fold_values"] == [
        {
            "fold_id": "wf-1",
            "value": {
                "mapping_entries": [
                    {
                        "key_type": "str",
                        "key": "scores",
                        "value": [1.0, 2.0],
                    }
                ]
            },
        },
        {
            "fold_id": "wf-2",
            "value": {
                "mapping_entries": [
                    {
                        "key_type": "str",
                        "key": "scores",
                        "value": [3.0, 4.0],
                    }
                ]
            },
        },
    ]
