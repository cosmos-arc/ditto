"""Runtime re-verification for the frozen research data feed."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import cast

import polars as pl

from ditto_application.processes.experiments.execution_bundle import (
    ExactBenchmarkBinding,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    FrozenResearchDataFrames,
    ResearchDataEvidenceManifest,
    VerifiedResearchFrame,
    research_data_error,
)

_EXPECTED_STATE_KEYS = frozenset(
    {
        "_snapshot",
        "_frames",
        "_start_date",
        "_end_date",
        "_knowledge_lag_days",
        "_benchmark",
        "_benchmark_id",
        "_expected_manifest_hash",
        "_evidence_manifest",
    },
)
_FRAME_FIELDS = ("bars", "calendar", "membership", "fundamental", "classification")


class ResearchDataFeedVerificationMixin:
    """Expose an API callers must invoke through the concrete feed class."""

    def require_verified_state(
        self,
        *,
        expected_snapshot: ResearchSnapshotBinding,
        expected_start_date: str,
        expected_end_date: str,
        expected_knowledge_lag_days: int,
        expected_benchmark: ExactBenchmarkBinding | None,
        expected_manifest_hash: str | None,
    ) -> None:
        """Rebuild the feed and reject any runtime state or byte drift."""
        _require_verified_state(
            self,
            expected_snapshot=expected_snapshot,
            expected_start_date=expected_start_date,
            expected_end_date=expected_end_date,
            expected_knowledge_lag_days=expected_knowledge_lag_days,
            expected_benchmark=expected_benchmark,
            expected_manifest_hash=expected_manifest_hash,
        )


def _require_verified_state(
    feed: object,
    *,
    expected_snapshot: ResearchSnapshotBinding,
    expected_start_date: str,
    expected_end_date: str,
    expected_knowledge_lag_days: int,
    expected_benchmark: ExactBenchmarkBinding | None,
    expected_manifest_hash: str | None,
) -> None:
    _require_expected_values(
        expected_snapshot=expected_snapshot,
        expected_start_date=expected_start_date,
        expected_end_date=expected_end_date,
        expected_knowledge_lag_days=expected_knowledge_lag_days,
        expected_benchmark=expected_benchmark,
        expected_manifest_hash=expected_manifest_hash,
    )
    feed_type = import_module(
        "ditto_application.processes.experiments.research_data_feed",
    ).ResearchDataFeed
    state = _exact_feed_state(feed, feed_type)
    snapshot, frames = _require_bound_core_state(
        state,
        expected_snapshot=expected_snapshot,
        expected_start_date=expected_start_date,
        expected_end_date=expected_end_date,
        expected_knowledge_lag_days=expected_knowledge_lag_days,
    )
    benchmark = _require_bound_benchmark(state, expected_benchmark)
    manifest = _require_bound_manifest(state, expected_manifest_hash)
    fresh = feed_type(
        snapshot=replace(snapshot),
        frames=frames,
        start_date=expected_start_date,
        end_date=expected_end_date,
        knowledge_lag_days=expected_knowledge_lag_days,
        benchmark=None if benchmark is None else replace(benchmark),
        expected_manifest_hash=expected_manifest_hash,
    )
    fresh_state = cast("dict[str, object]", vars(cast("object", fresh)))
    if manifest != fresh_state["_evidence_manifest"]:
        _drift("evidence_manifest")
    _require_reparsed_frames(frames, fresh_state["_frames"])


def _exact_feed_state(feed: object, feed_type: type[object]) -> dict[str, object]:
    if type(feed) is not feed_type:
        _drift("type")
    state = cast("dict[str, object]", vars(feed))
    actual_keys = frozenset(state)
    if actual_keys != _EXPECTED_STATE_KEYS:
        _drift(
            "state_keys",
            missing=sorted(_EXPECTED_STATE_KEYS - actual_keys),
            unexpected=sorted(actual_keys - _EXPECTED_STATE_KEYS),
        )
    return state


def _require_bound_core_state(
    state: dict[str, object],
    *,
    expected_snapshot: ResearchSnapshotBinding,
    expected_start_date: str,
    expected_end_date: str,
    expected_knowledge_lag_days: int,
) -> tuple[ResearchSnapshotBinding, FrozenResearchDataFrames]:
    snapshot = state["_snapshot"]
    frames = state["_frames"]
    if type(snapshot) is not ResearchSnapshotBinding or snapshot != expected_snapshot:
        _drift("snapshot")
    if type(frames) is not FrozenResearchDataFrames:
        _drift("frames")
    if (
        type(state["_start_date"]) is not str
        or state["_start_date"] != expected_start_date
    ):
        _drift("start_date")
    if type(state["_end_date"]) is not str or state["_end_date"] != expected_end_date:
        _drift("end_date")
    if (
        type(state["_knowledge_lag_days"]) is not int
        or state["_knowledge_lag_days"] != expected_knowledge_lag_days
    ):
        _drift("knowledge_lag_days")
    return cast("ResearchSnapshotBinding", snapshot), cast(
        "FrozenResearchDataFrames",
        frames,
    )


def _require_bound_benchmark(
    state: dict[str, object],
    expected_benchmark: ExactBenchmarkBinding | None,
) -> ExactBenchmarkBinding | None:
    benchmark = state["_benchmark"]
    if benchmark != expected_benchmark or (
        benchmark is not None and type(benchmark) is not ExactBenchmarkBinding
    ):
        _drift("benchmark")
    expected_benchmark_id = (
        None if expected_benchmark is None else expected_benchmark.instrument_id
    )
    if state["_benchmark_id"] != expected_benchmark_id or (
        state["_benchmark_id"] is not None and type(state["_benchmark_id"]) is not int
    ):
        _drift("benchmark_id")
    return cast("ExactBenchmarkBinding | None", benchmark)


def _require_bound_manifest(
    state: dict[str, object],
    expected_manifest_hash: str | None,
) -> ResearchDataEvidenceManifest:
    if state["_expected_manifest_hash"] != expected_manifest_hash or (
        state["_expected_manifest_hash"] is not None
        and type(state["_expected_manifest_hash"]) is not str
    ):
        _drift("expected_manifest_hash")
    manifest = state["_evidence_manifest"]
    if type(manifest) is not ResearchDataEvidenceManifest:
        _drift("evidence_manifest")
    return cast("ResearchDataEvidenceManifest", manifest)


def _require_expected_values(
    *,
    expected_snapshot: object,
    expected_start_date: object,
    expected_end_date: object,
    expected_knowledge_lag_days: object,
    expected_benchmark: object,
    expected_manifest_hash: object,
) -> None:
    if type(expected_snapshot) is not ResearchSnapshotBinding:
        _drift("expected_snapshot")
    if type(expected_start_date) is not str:
        _drift("expected_start_date")
    if type(expected_end_date) is not str:
        _drift("expected_end_date")
    if type(expected_knowledge_lag_days) is not int:
        _drift("expected_knowledge_lag_days")
    if expected_benchmark is not None and type(expected_benchmark) is not (
        ExactBenchmarkBinding
    ):
        _drift("expected_benchmark")
    if expected_manifest_hash is not None and type(expected_manifest_hash) is not str:
        _drift("expected_manifest_hash")


def _require_reparsed_frames(
    current: FrozenResearchDataFrames,
    fresh: object,
) -> None:
    if type(fresh) is not FrozenResearchDataFrames:
        _drift("frames")
    for field_name in _FRAME_FIELDS:
        current_frame = getattr(current, field_name)
        fresh_frame = getattr(fresh, field_name)
        if current_frame is None or fresh_frame is None:
            if current_frame is not fresh_frame:
                _drift(field_name)
            continue
        if (
            type(current_frame) is not VerifiedResearchFrame
            or type(fresh_frame) is not VerifiedResearchFrame
            or current_frame != fresh_frame
        ):
            _drift(field_name)
        if type(
            current_frame.frame
        ) is not pl.DataFrame or not current_frame.frame.equals(fresh_frame.frame):
            _drift(f"{field_name}.frame")


def _drift(field: str, **details: object) -> None:
    raise research_data_error(
        "research data feed runtime state drifted from frozen evidence",
        "research_data_feed_state_drift",
        field=field,
        **details,
    )
