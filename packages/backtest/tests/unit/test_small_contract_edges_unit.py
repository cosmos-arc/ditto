"""Small fail-closed branches at backtest serialization boundaries."""

from __future__ import annotations

from typing import cast

import pytest
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_backtest.provenance import aggregate_source_snapshot_id
from ditto_backtest.steps.input_bundle import build_input_bundle


def _artifact(**changes: object) -> ReplayArtifactRef:
    values: dict[str, object] = {
        "artifact_id": "summary-1",
        "artifact_kind": "summary",
        "artifact_format": "json",
        "content_hash": "a" * 64,
        "schema_hash": "b" * 64,
        "row_count": 1,
        "byte_size": 10,
    }
    values.update(changes)
    return ReplayArtifactRef(
        artifact_id=cast(str, values["artifact_id"]),
        artifact_kind=cast(str, values["artifact_kind"]),
        artifact_format=cast(str, values["artifact_format"]),
        content_hash=cast(str, values["content_hash"]),
        schema_hash=cast(str, values["schema_hash"]),
        row_count=cast(int, values["row_count"]),
        byte_size=cast(int, values["byte_size"]),
    )


def test_extra_instrument_columns_are_preserved_for_an_empty_universe() -> None:
    bundle = build_input_bundle(
        "2026-09-04",
        "strategy-1",
        "run-1",
        {},
        extra_instrument_columns={"sector_id": []},
    )

    assert bundle.instruments.columns == ["instrument_id", "sector_id"]


def test_empty_snapshot_collection_has_no_aggregate_identity() -> None:
    assert aggregate_source_snapshot_id((None, " ")) is None


@pytest.mark.parametrize("field", ["artifact_id", "artifact_kind"])
def test_replay_artifact_identity_rejects_path_like_values(field: str) -> None:
    with pytest.raises(ValueError, match="canonical identity"):
        _artifact(**{field: "directory/value"})


@pytest.mark.parametrize("field", ["row_count", "byte_size"])
def test_replay_artifact_counts_require_exact_nonnegative_integers(field: str) -> None:
    with pytest.raises(ValueError, match="nonnegative exact integer"):
        _artifact(**{field: True})


def test_replay_evidence_requires_nonempty_exact_artifact_tuple() -> None:
    with pytest.raises(ValueError, match="non-empty tuple"):
        ResearchReplayEvidence(
            reproduction_fingerprint="f" * 64,
            key_result_summary_artifact_id="summary-1",
            required_artifacts=(),
        )

    with pytest.raises(ValueError, match="exact ReplayArtifactRef"):
        ResearchReplayEvidence(
            reproduction_fingerprint="f" * 64,
            key_result_summary_artifact_id="summary-1",
            required_artifacts=(cast(ReplayArtifactRef, object()),),
        )
