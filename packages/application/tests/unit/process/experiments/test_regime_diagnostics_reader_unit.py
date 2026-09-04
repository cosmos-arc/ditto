"""PIT-safe regime diagnostics over one immutable research bars artifact."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO

import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.regime_diagnostics_reader import (
    RegimeDiagnosticsReader,
    RegimeDiagnosticsScope,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    research_artifact_content_hash,
    research_frame_schema_hash,
)


@dataclass(frozen=True)
class _Artifacts:
    values: dict[str, bytes]

    def read_frozen_research_input_bytes(self, artifact_id: str) -> bytes:
        return self.values[artifact_id]


def _bars(*, future_close: float) -> bytes:
    start = date(2026, 1, 1)
    dates = [start + timedelta(days=index) for index in range(26)]
    closes = [100.0 + index for index in range(25)] + [future_close]
    frame = pl.DataFrame(
        {
            "trade_date": dates,
            "instrument_id": [300_001] * len(dates),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "prev_close": closes,
            "volume": [1_000.0] * len(dates),
            "amount": [100_000.0] * len(dates),
            "is_suspended": [False] * len(dates),
            "limit_up": [200.0] * len(dates),
            "limit_down": [50.0] * len(dates),
            "avg_volume_20d": [1_000.0] * len(dates),
            "source_snapshot_id": ["provider-bars-v1"] * len(dates),
        }
    )
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _artifacts(*, future_close: float) -> tuple[_Artifacts, str]:
    bars = _bars(future_close=future_close)
    bars_frame = pl.read_parquet(BytesIO(bars))
    inputs = [
        {
            "input_id": "bars-regime-1",
            "artifact_kind": "bars",
            "content_hash": research_artifact_content_hash(bars),
            "schema_hash": research_frame_schema_hash(bars_frame),
        },
        {
            "input_id": "calendar-regime-1",
            "artifact_kind": "calendar",
            "content_hash": "2" * 64,
            "schema_hash": "b" * 64,
        },
        {
            "input_id": "instrument-rules-regime-1",
            "artifact_kind": "instrument_rules",
            "content_hash": "3" * 64,
            "schema_hash": "c" * 64,
        },
        {
            "input_id": "membership-regime-1",
            "artifact_kind": "membership",
            "content_hash": "4" * 64,
            "schema_hash": "d" * 64,
        },
    ]
    payload = {
        "schema_version": 1,
        "snapshot_id": "snapshot-regime-1",
        "dataset_id": "research-index-daily",
        "source_snapshot_ids": ["provider-bars-v1"],
        "known_at_policy": "sample_time",
        "builder_version": "research-snapshot-builder-v1",
        "inputs": inputs,
    }
    manifest = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    return (
        _Artifacts(
            {
                "snapshot-regime-1": manifest,
                "bars-regime-1": bars,
            }
        ),
        manifest_hash,
    )


def _scope(manifest_hash: str) -> RegimeDiagnosticsScope:
    return RegimeDiagnosticsScope(
        snapshot_id="snapshot-regime-1",
        snapshot_manifest_hash=manifest_hash,
        benchmark_instrument_id=300_001,
        start_date=date(2026, 1, 21),
        end_date=date(2026, 1, 25),
        knowledge_cutoff=date(2026, 1, 26),
    )


@pytest.mark.pit
def test_regime_diagnostics_excludes_cutoff_day_future_sentinel() -> None:
    baseline_artifacts, baseline_hash = _artifacts(future_close=125.0)
    sentinel_artifacts, sentinel_hash = _artifacts(future_close=99_999.0)

    baseline = RegimeDiagnosticsReader(baseline_artifacts).read(_scope(baseline_hash))
    sentinel = RegimeDiagnosticsReader(sentinel_artifacts).read(_scope(sentinel_hash))

    assert baseline.observations == sentinel.observations
    assert baseline.transitions == sentinel.transitions
    assert baseline.current.observed_at == date(2026, 1, 25)
    assert baseline.current.label.value == "bull"
    assert baseline.bear_threshold == 35.0
    assert baseline.bull_threshold == 65.0
    assert baseline.source_snapshot_ids == ("provider-bars-v1",)
    assert baseline.bars_input_id == "bars-regime-1"


def test_regime_scope_rejects_same_day_close_as_known() -> None:
    _artifacts_reader, manifest_hash = _artifacts(future_close=125.0)

    with pytest.raises(AppProcessError) as exc_info:
        RegimeDiagnosticsScope(
            snapshot_id="snapshot-regime-1",
            snapshot_manifest_hash=manifest_hash,
            benchmark_instrument_id=300_001,
            start_date=date(2026, 1, 21),
            end_date=date(2026, 1, 26),
            knowledge_cutoff=date(2026, 1, 26),
        )

    assert exc_info.value.details["reason"] == "regime_end_not_before_cutoff"
