"""Content-addressed Research Case contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from ditto_analysis.research.cases import ResearchCase
from ditto_kernel.identity import InstrumentId

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _case(**overrides: object) -> ResearchCase:
    baseline = ResearchCase(
        selection_run_id=f"selection-run:sha256:{_HASH_A}",
        selection_run_hash=_HASH_A,
        selection_input_hash=_HASH_B,
        selection_spec_hash="c" * 64,
        objective="Validate whether the selected momentum leaders persist.",
        asset_kind="stock",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-b", "source-a"),
        candidate_instrument_ids=(
            InstrumentId(600001),
            InstrumentId(600002),
        ),
        selection_status="ready",
        missing_inputs=(),
    )
    return replace(baseline, **overrides)


def test_research_case_is_canonical_content_addressed_and_immutable() -> None:
    case = _case()
    equivalent = _case(source_snapshot_ids=("source-a", "source-b"))

    assert case.source_snapshot_ids == ("source-a", "source-b")
    assert case.case_id == equivalent.case_id
    assert case.case_id.startswith("research-case:sha256:")
    with pytest.raises(FrozenInstanceError):
        cast(Any, case).objective = "changed"


def test_research_case_identity_tracks_selection_temporal_and_candidate_lineage() -> (
    None
):
    baseline = _case()

    for changed in (
        replace(
            baseline,
            selection_run_id=f"selection-run:sha256:{'d' * 64}",
            selection_run_hash="d" * 64,
        ),
        replace(
            baseline,
            knowledge_cutoff=datetime(2026, 8, 30, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 30, tzinfo=UTC),
        ),
        replace(baseline, candidate_instrument_ids=(InstrumentId(600001),)),
        replace(baseline, objective="Test a different hypothesis."),
    ):
        assert changed.case_id != baseline.case_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"selection_run_hash": "short"},
        {"source_snapshot_ids": ()},
        {"candidate_instrument_ids": ()},
        {
            "candidate_instrument_ids": (
                InstrumentId(600001),
                InstrumentId(600001),
            )
        },
        {"knowledge_cutoff": datetime(2026, 9, 1, tzinfo=UTC)},
        {"selection_status": "blocked"},
    ],
)
def test_research_case_rejects_incomplete_or_non_pit_lineage(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _case(**overrides)
