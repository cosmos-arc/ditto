"""Frozen exact/PIT research DataFeed adapter tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from inspect import Parameter, signature
from io import BytesIO

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import research_data_feed as feed_module
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)
from ditto_application.processes.experiments.research_data_feed import (
    FrozenResearchDataFrames,
    ResearchDataFeed,
    ResearchFrameKind,
    VerifiedResearchFrame,
)
from ditto_backtest.data_feed import DataFeed
from ditto_kernel.identity import InstrumentId


def _parquet_bytes(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _benchmark_binding(
    frames: FrozenResearchDataFrames,
) -> tuple[ContentAddressedResearchInput, ExactBenchmarkBinding]:
    mapping = ContentAddressedResearchInput(
        input_id="instrument_rules",
        artifact_kind="instrument_rules",
        content_hash="8" * 64,
        schema_hash="9" * 64,
    )
    return mapping, ExactBenchmarkBinding(
        instrument_id=99,
        instrument_identity_hash="a" * 64,
        mapping_input=mapping,
        bars_input=frames.bars.input_evidence,
    )


def _artifact_input(
    kind: ResearchFrameKind,
    artifact_bytes: bytes,
    frame: pl.DataFrame,
    *,
    input_id: str | None = None,
    schema_hash: str | None = None,
) -> ContentAddressedResearchInput:
    return ContentAddressedResearchInput(
        input_id=input_id or f"{kind.value}.parquet",
        artifact_kind=kind.value,
        content_hash=feed_module.research_artifact_content_hash(artifact_bytes),
        schema_hash=schema_hash or feed_module.research_frame_schema_hash(frame),
    )


def _source_id(kind: ResearchFrameKind) -> str:
    return f"snapshot:frozen:{kind.value}:v1"


def _verified(
    kind: ResearchFrameKind,
    frame: pl.DataFrame,
    *,
    input_id: str | None = None,
    source_snapshot_ids: tuple[str, ...] | None = None,
) -> VerifiedResearchFrame:
    artifact_bytes = _parquet_bytes(frame)
    input_evidence = _artifact_input(
        kind,
        artifact_bytes,
        frame,
        input_id=input_id,
    )
    return VerifiedResearchFrame(
        input_evidence=input_evidence,
        source_snapshot_ids=source_snapshot_ids or (_source_id(kind),),
        artifact_bytes=artifact_bytes,
    )


def _calendar(*dates: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": dates,
            "is_open": [True] * len(dates),
            "source_snapshot_id": [_source_id(ResearchFrameKind.CALENDAR)] * len(dates),
        },
    )


def _bars(rows: tuple[tuple[str, int, float], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [item[0] for item in rows],
            "instrument_id": [item[1] for item in rows],
            "open": [item[2] - 0.1 for item in rows],
            "high": [item[2] + 0.5 for item in rows],
            "low": [item[2] - 0.5 for item in rows],
            "close": [item[2] for item in rows],
            "prev_close": [item[2] - 0.2 for item in rows],
            "volume": [100_000.0] * len(rows),
            "amount": [1_000_000.0] * len(rows),
            "is_suspended": [False] * len(rows),
            "limit_up": [item[2] * 1.1 for item in rows],
            "limit_down": [item[2] * 0.9 for item in rows],
            "avg_volume_20d": [90_000.0] * len(rows),
            "source_snapshot_id": [_source_id(ResearchFrameKind.BARS)] * len(rows),
        },
    )


def _membership(rows: tuple[tuple[str, int, bool], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [item[0] for item in rows],
            "instrument_id": [item[1] for item in rows],
            "is_member": [item[2] for item in rows],
            "known_at": [item[0] for item in rows],
            "source_snapshot_id": [_source_id(ResearchFrameKind.MEMBERSHIP)]
            * len(rows),
        },
    )


def _fundamentals(
    rows: tuple[tuple[int, str, float, float, float], ...],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [item[0] for item in rows],
            "known_at": [item[1] for item in rows],
            "roe": [item[2] for item in rows],
            "net_margin": [item[3] for item in rows],
            "eps": [item[4] for item in rows],
            "source_snapshot_id": [_source_id(ResearchFrameKind.FUNDAMENTAL)]
            * len(rows),
        },
    )


def _classifications(rows: tuple[tuple[int, str, str], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [item[0] for item in rows],
            "known_at": [item[1] for item in rows],
            "sector_id": [item[2] for item in rows],
            "source_snapshot_id": [_source_id(ResearchFrameKind.CLASSIFICATION)]
            * len(rows),
        },
    )


def _snapshot(
    frames: FrozenResearchDataFrames,
    *,
    inputs: tuple[ContentAddressedResearchInput, ...] | None = None,
    known_at_policy: str = "sample_time",
    extra_inputs: tuple[ContentAddressedResearchInput, ...] = (),
) -> ResearchSnapshotBinding:
    frame_items = frames.items()
    return ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot(
            snapshot_id="research-snapshot-exact-v1",
            manifest_hash="f" * 64,
        ),
        dataset_id="a-share-research-v1",
        source_snapshot_ids=tuple(
            sorted(
                {
                    source_id
                    for _, verified in frame_items
                    for source_id in verified.source_snapshot_ids
                },
            ),
        ),
        known_at_policy=known_at_policy,
        builder_version="research-frame-fixture-v1",
        inputs=(
            inputs
            if inputs is not None
            else tuple(item.input_evidence for _, item in frame_items) + extra_inputs
        ),
    )


def _minimal_frames() -> FrozenResearchDataFrames:
    dates = ("2026-01-02", "2026-01-05")
    return FrozenResearchDataFrames(
        bars=_verified(
            ResearchFrameKind.BARS,
            _bars(((dates[0], 1, 10.0), (dates[1], 1, 11.0))),
        ),
        calendar=_verified(ResearchFrameKind.CALENDAR, _calendar(*dates)),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            _membership(((dates[0], 1, True), (dates[1], 1, True))),
        ),
    )


def _minimal_feed() -> ResearchDataFeed:
    dates = ("2026-01-02", "2026-01-05")
    frames = _minimal_frames()
    return ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date=dates[0],
        end_date=dates[1],
        knowledge_lag_days=0,
    )


def test_trading_days_come_only_from_frozen_calendar_window() -> None:
    feed = _minimal_feed()

    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]
    parameters = signature(ResearchDataFeed).parameters
    assert "provider" not in parameters
    assert "benchmark" in parameters
    assert "benchmark_id" not in parameters


def test_feed_requires_an_explicit_exact_nonnegative_knowledge_lag() -> None:
    frames = _minimal_frames()
    parameters = signature(ResearchDataFeed).parameters

    assert parameters["knowledge_lag_days"].default is Parameter.empty
    for invalid in (-1, True, 1.0):
        with pytest.raises(AppProcessError) as exc_info:
            ResearchDataFeed(
                snapshot=_snapshot(frames),
                frames=frames,
                start_date="2026-01-02",
                end_date="2026-01-05",
                knowledge_lag_days=invalid,  # type: ignore[arg-type]
            )
        assert exc_info.value.details["reason"] == "invalid_knowledge_lag_days"


def test_membership_knowledge_lag_allows_zero_and_rejects_same_day_at_one() -> None:
    frames = _minimal_frames()

    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )
    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=1,
        )

    assert exc_info.value.details["reason"] == "membership_knowledge_lag_violation"


def test_membership_lag_failure_keeps_datetime_evidence_typed() -> None:
    frames = _minimal_frames()
    datetime_membership = _verified(
        ResearchFrameKind.MEMBERSHIP,
        frames.membership.frame.with_columns(
            pl.col("trade_date").str.to_datetime(),
            pl.col("known_at").str.to_datetime(),
        ),
    )
    invalid_frames = replace(frames, membership=datetime_membership)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=1,
        )

    assert exc_info.value.details["reason"] == "membership_knowledge_lag_violation"


def test_verified_frame_rejects_exact_parquet_byte_mismatch() -> None:
    verified = _verified(
        ResearchFrameKind.CALENDAR,
        _calendar("2026-01-02"),
    )

    with pytest.raises(AppProcessError) as exc_info:
        replace(verified, artifact_bytes=verified.artifact_bytes + b"tampered")

    assert exc_info.value.details["reason"] == "frame_content_hash_mismatch"


def test_verified_frame_rejects_parsed_schema_hash_mismatch() -> None:
    original = _verified(
        ResearchFrameKind.CALENDAR,
        _calendar("2026-01-02"),
    )
    reordered = original.frame.select(
        "source_snapshot_id",
        "trade_date",
        "is_open",
    )
    artifact_bytes = _parquet_bytes(reordered)
    evidence = replace(
        original.input_evidence,
        content_hash=feed_module.research_artifact_content_hash(artifact_bytes),
    )

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchFrame(
            input_evidence=evidence,
            source_snapshot_ids=original.source_snapshot_ids,
            artifact_bytes=artifact_bytes,
        )

    assert exc_info.value.details["reason"] == "frame_schema_hash_mismatch"


def test_adapter_rejects_frame_bound_under_the_wrong_artifact_kind() -> None:
    frames = _minimal_frames()
    wrong_bars = _verified(
        ResearchFrameKind.CALENDAR,
        _calendar("2026-01-02", "2026-01-05"),
    )

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames),
            frames=replace(frames, bars=wrong_bars),
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "research_frame_kind_mismatch"


def test_adapter_rejects_frame_not_bound_to_exact_snapshot_inputs() -> None:
    frames = _minimal_frames()
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(
                frames,
                inputs=(
                    frames.calendar.input_evidence,
                    frames.membership.input_evidence,
                ),
            ),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "frame_not_bound_to_exact_snapshot"


def test_adapter_rejects_frame_source_outside_snapshot_source_set() -> None:
    frames = _minimal_frames()
    bars = replace(
        frames.bars,
        source_snapshot_ids=("snapshot:unbound:bars:v9",),
    )

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames),
            frames=replace(frames, bars=bars),
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "unbound_frame_source_snapshot"


def test_snapshot_declared_optional_feed_artifact_must_be_supplied() -> None:
    frames = _minimal_frames()
    fundamental = _verified(
        ResearchFrameKind.FUNDAMENTAL,
        _fundamentals(((1, "2026-01-01", 0.1, 0.2, 1.0),)),
    )

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(
                frames,
                extra_inputs=(fundamental.input_evidence,),
            ),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "missing_declared_research_frame"
    assert exc_info.value.details["frame_kind"] == "fundamental"


def test_snapshot_rejects_duplicate_supported_feed_artifact_kind() -> None:
    frames = _minimal_frames()
    duplicate_bars = replace(
        frames.bars.input_evidence,
        input_id="bars-copy.parquet",
    )

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames, extra_inputs=(duplicate_bars,)),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "duplicate_feed_artifact_kind"
    assert exc_info.value.details["frame_kind"] == "bars"


def test_snapshot_may_retain_non_feed_artifacts() -> None:
    frames = _minimal_frames()
    non_feed = ContentAddressedResearchInput(
        input_id="factor-matrix.parquet",
        artifact_kind="factor_matrix",
        content_hash="8" * 64,
        schema_hash="9" * 64,
    )

    feed = ResearchDataFeed(
        snapshot=_snapshot(frames, extra_inputs=(non_feed,)),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]


def test_feed_accepts_sample_time_known_at_policy() -> None:
    frames = _minimal_frames()

    feed = ResearchDataFeed(
        snapshot=_snapshot(frames, known_at_policy="sample_time"),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]


def test_feed_rejects_explicit_cutoff_without_timestamp_contract() -> None:
    frames = _minimal_frames()

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames, known_at_policy="explicit_cutoff"),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "unsupported_known_at_policy"


def test_feed_rejects_unsupported_known_at_policy() -> None:
    frames = _minimal_frames()

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(
                frames,
                known_at_policy="known_at_lte_as_of_fail_closed",
            ),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "unsupported_known_at_policy"


@pytest.mark.parametrize(
    ("kind", "missing_column"),
    [
        pytest.param(ResearchFrameKind.BARS, "close", id="bars"),
        pytest.param(ResearchFrameKind.CALENDAR, "is_open", id="calendar"),
        pytest.param(ResearchFrameKind.MEMBERSHIP, "known_at", id="membership"),
    ],
)
def test_required_frames_fail_closed_on_missing_schema_columns(
    kind: ResearchFrameKind,
    missing_column: str,
) -> None:
    frames = _minimal_frames()
    original = getattr(frames, kind.value)
    invalid = _verified(kind, original.frame.drop(missing_column))
    invalid_frames = replace(frames, **{kind.value: invalid})

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "missing_frozen_frame_columns"
    assert exc_info.value.details["frame_kind"] == kind.value


def test_required_frames_fail_closed_on_incompatible_column_dtype() -> None:
    frames = _minimal_frames()
    bad_bars = _verified(
        ResearchFrameKind.BARS,
        frames.bars.frame.with_columns(
            pl.col("instrument_id").cast(pl.String),
        ),
    )
    invalid_frames = replace(frames, bars=bad_bars)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "invalid_frozen_frame_schema"
    assert exc_info.value.details["column"] == "instrument_id"


@pytest.mark.parametrize(
    ("kind", "column"),
    [
        pytest.param(ResearchFrameKind.BARS, "close", id="bars-close"),
        pytest.param(ResearchFrameKind.CALENDAR, "is_open", id="calendar-open"),
        pytest.param(
            ResearchFrameKind.MEMBERSHIP,
            "known_at",
            id="membership-known-at",
        ),
        pytest.param(
            ResearchFrameKind.MEMBERSHIP,
            "is_member",
            id="membership-flag",
        ),
        pytest.param(ResearchFrameKind.FUNDAMENTAL, "roe", id="fundamental-roe"),
        pytest.param(
            ResearchFrameKind.CLASSIFICATION,
            "sector_id",
            id="classification-sector",
        ),
    ],
)
def test_every_required_column_rejects_null(
    kind: ResearchFrameKind,
    column: str,
) -> None:
    base = _minimal_frames()
    frames = replace(
        base,
        fundamental=_verified(
            ResearchFrameKind.FUNDAMENTAL,
            _fundamentals(((1, "2026-01-01", 0.1, 0.2, 1.0),)),
        ),
        classification=_verified(
            ResearchFrameKind.CLASSIFICATION,
            _classifications(((1, "2026-01-01", "bank"),)),
        ),
    )
    original = getattr(frames, kind.value)
    null_frame = original.frame.with_columns(
        pl.lit(None, dtype=original.frame.schema[column]).alias(column),
    )
    invalid = _verified(kind, null_frame)
    invalid_frames = replace(frames, **{kind.value: invalid})

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "null_frozen_frame_column"
    assert exc_info.value.details["columns"] == [column]


@pytest.mark.parametrize(
    "value", [pytest.param(float("nan")), pytest.param(float("inf"))]
)
def test_numeric_required_columns_reject_non_finite_values(value: float) -> None:
    frames = _minimal_frames()
    bad_bars = _verified(
        ResearchFrameKind.BARS,
        frames.bars.frame.with_columns(pl.lit(value).alias("close")),
    )
    invalid_frames = replace(frames, bars=bad_bars)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "non_finite_frozen_numeric"
    assert exc_info.value.details["columns"] == ["close"]


def test_row_source_snapshot_must_match_verified_frame_evidence() -> None:
    frames = _minimal_frames()
    bad_bars = _verified(
        ResearchFrameKind.BARS,
        frames.bars.frame.with_columns(
            pl.lit("snapshot:unverified:row:v2").alias("source_snapshot_id"),
        ),
        source_snapshot_ids=frames.bars.source_snapshot_ids,
    )
    invalid_frames = replace(frames, bars=bad_bars)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "row_source_snapshot_mismatch"


def test_slice_contains_only_that_days_pit_members() -> None:
    dates = ("2026-01-02", "2026-01-05")
    frames = FrozenResearchDataFrames(
        bars=_verified(
            ResearchFrameKind.BARS,
            _bars(
                (
                    (dates[0], 1, 10.0),
                    (dates[0], 2, 20.0),
                    (dates[1], 1, 11.0),
                    (dates[1], 2, 21.0),
                ),
            ),
        ),
        calendar=_verified(ResearchFrameKind.CALENDAR, _calendar(*dates)),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            _membership(
                (
                    (dates[0], 1, True),
                    (dates[0], 2, False),
                    (dates[1], 1, True),
                    (dates[1], 2, True),
                ),
            ),
        ),
    )
    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date=dates[0],
        end_date=dates[1],
        knowledge_lag_days=0,
    )

    first = feed.get_slice(dates[0])
    second = feed.get_slice(dates[1])

    assert set(first.bars) == {InstrumentId(1)}
    assert set(second.bars) == {InstrumentId(1), InstrumentId(2)}
    assert first.bars[InstrumentId(1)].close == pytest.approx(10.0)
    assert first.step_time.isoformat() == "2026-01-02T15:00:00+00:00"
    assert first.source_snapshot_ids == {
        InstrumentId(1): _source_id(ResearchFrameKind.BARS),
    }


def test_membership_known_at_cannot_be_after_membership_trade_date() -> None:
    frames = _minimal_frames()
    invalid_membership = _verified(
        ResearchFrameKind.MEMBERSHIP,
        frames.membership.frame.with_columns(
            pl.when(pl.col("trade_date") == "2026-01-02")
            .then(pl.lit("2026-01-03"))
            .otherwise(pl.col("known_at"))
            .alias("known_at"),
        ),
    )
    invalid_frames = replace(frames, membership=invalid_membership)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "membership_knowledge_lag_violation"


def test_active_member_without_exact_bar_fails_closed() -> None:
    frames = _minimal_frames()
    membership = _verified(
        ResearchFrameKind.MEMBERSHIP,
        _membership(
            (
                ("2026-01-02", 1, True),
                ("2026-01-02", 2, True),
                ("2026-01-05", 1, True),
            ),
        ),
    )
    invalid_frames = replace(frames, membership=membership)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "missing_exact_member_bar"


def _history_feed(
    *, short_history_for_second_instrument: bool = False
) -> ResearchDataFeed:
    dates = (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
    )
    bars = tuple(
        (trade_date, instrument_id, float(10 * instrument_id + ordinal))
        for ordinal, trade_date in enumerate(dates)
        for instrument_id in (1, 2)
        if not (
            short_history_for_second_instrument and instrument_id == 2 and ordinal < 3
        )
    )
    membership = tuple(
        (trade_date, instrument_id, instrument_id == 1 or ordinal >= 3)
        for ordinal, trade_date in enumerate(dates)
        for instrument_id in (1, 2)
    )
    frames = FrozenResearchDataFrames(
        bars=_verified(ResearchFrameKind.BARS, _bars(bars)),
        calendar=_verified(ResearchFrameKind.CALENDAR, _calendar(*dates)),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            _membership(membership),
        ),
    )
    return ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date="2026-01-08",
        end_date="2026-01-08",
        knowledge_lag_days=0,
    )


def test_history_is_strict_as_of_for_current_pit_members() -> None:
    feed = _history_feed()

    result = feed.get_history(
        [InstrumentId(1), InstrumentId(2)],
        "2026-01-08",
        1,
    )

    assert result.select("instrument_id", "trade_date").rows() == [
        (1, "2026-01-07"),
        (2, "2026-01-07"),
    ]


def test_history_uses_frozen_pre_membership_prices_for_current_member_warmup() -> None:
    feed = _history_feed()

    result = feed.get_history(
        [InstrumentId(1), InstrumentId(2)],
        "2026-01-08",
        3,
    )

    assert result.select("instrument_id", "trade_date").rows() == [
        (1, "2026-01-05"),
        (1, "2026-01-06"),
        (1, "2026-01-07"),
        (2, "2026-01-05"),
        (2, "2026-01-06"),
        (2, "2026-01-07"),
    ]


def test_history_accepts_next_session_member_known_at_lagged_cutoff() -> None:
    """A member effective tomorrow is usable when frozen evidence is known today."""
    dates = ("2026-01-06", "2026-01-07", "2026-01-08")
    membership = pl.DataFrame(
        {
            "trade_date": list(dates),
            "instrument_id": [2, 2, 2],
            "is_member": [False, False, True],
            "known_at": ["2026-01-05", "2026-01-06", "2026-01-07"],
            "source_snapshot_id": [
                _source_id(ResearchFrameKind.MEMBERSHIP),
            ]
            * 3,
        }
    )
    frames = FrozenResearchDataFrames(
        bars=_verified(
            ResearchFrameKind.BARS,
            _bars(
                (
                    (dates[0], 2, 20.0),
                    (dates[1], 2, 21.0),
                    (dates[2], 2, 22.0),
                )
            ),
        ),
        calendar=_verified(ResearchFrameKind.CALENDAR, _calendar(*dates)),
        membership=_verified(ResearchFrameKind.MEMBERSHIP, membership),
    )
    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date=dates[2],
        end_date=dates[2],
        knowledge_lag_days=1,
    )

    assert set(feed.get_slice(dates[2]).bars) == {InstrumentId(2)}
    history = feed.get_history([InstrumentId(2)], dates[1], 1)
    assert history.select("instrument_id", "trade_date").rows() == [
        (2, dates[0]),
    ]


def test_history_rejects_instrument_outside_current_pit_membership() -> None:
    feed = _history_feed()

    with pytest.raises(AppProcessError) as exc_info:
        feed.get_history(
            [InstrumentId(2)],
            "2026-01-06",
            1,
        )

    assert exc_info.value.details["reason"] == "history_request_outside_pit_membership"
    assert exc_info.value.details["instrument_ids"] == [2]


def test_history_still_fails_closed_when_frozen_prices_lack_full_lookback() -> None:
    feed = _history_feed(short_history_for_second_instrument=True)

    with pytest.raises(AppProcessError) as exc_info:
        feed.get_history(
            [InstrumentId(2)],
            "2026-01-08",
            3,
        )

    assert exc_info.value.details["reason"] == "insufficient_frozen_history"
    assert exc_info.value.details["instrument_ids"] == [2]


def test_history_requires_canonical_iso_as_of_even_for_empty_request() -> None:
    feed = _history_feed()

    with pytest.raises(AppProcessError) as exc_info:
        feed.get_history([], "2026/01/08", 0)

    assert exc_info.value.details["reason"] == "invalid_execution_window"
    assert exc_info.value.details["field"] == "as_of_date"


def test_history_uses_only_exact_frozen_open_calendar_sessions() -> None:
    dates = ("2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05")
    calendar = _calendar(dates[0], dates[1], dates[3]).with_columns(
        pl.when(pl.col("trade_date") == dates[1])
        .then(pl.lit(False))
        .otherwise(pl.col("is_open"))
        .alias("is_open"),
    )
    frames = FrozenResearchDataFrames(
        bars=_verified(
            ResearchFrameKind.BARS,
            _bars(tuple((item, 1, float(index)) for index, item in enumerate(dates))),
        ),
        calendar=_verified(ResearchFrameKind.CALENDAR, calendar),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            _membership(tuple((item, 1, True) for item in dates)),
        ),
    )
    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date=dates[3],
        end_date=dates[3],
        knowledge_lag_days=0,
    )

    result = feed.get_history([InstrumentId(1)], "2026-01-06", 2)

    assert result["trade_date"].to_list() == ["2026-01-02", "2026-01-05"]


def test_optional_pit_frame_calls_fail_closed_when_not_frozen() -> None:
    feed = _minimal_feed()

    with pytest.raises(AppProcessError) as fundamental_error:
        feed.get_fundamental_snapshot([InstrumentId(1)], date(2026, 1, 4))
    with pytest.raises(AppProcessError) as classification_error:
        feed.get_classification_snapshot([InstrumentId(1)], date(2026, 1, 4))

    assert fundamental_error.value.details["reason"] == "missing_frozen_pit_frame"
    assert classification_error.value.details["reason"] == "missing_frozen_pit_frame"


def _pit_snapshot_feed() -> ResearchDataFeed:
    base = _minimal_frames()
    frames = replace(
        base,
        fundamental=_verified(
            ResearchFrameKind.FUNDAMENTAL,
            _fundamentals(
                (
                    (1, "2026-01-01", 0.10, 0.08, 1.0),
                    (1, "2026-01-04", 0.20, 0.09, 1.2),
                    (1, "2026-01-10", 0.99, 0.99, 9.9),
                    (2, "2026-01-03", 0.30, 0.10, 1.4),
                ),
            ),
        ),
        classification=_verified(
            ResearchFrameKind.CLASSIFICATION,
            _classifications(
                (
                    (1, "2026-01-01", "bank-old"),
                    (1, "2026-01-04", "bank-new"),
                    (2, "2026-01-03", "technology"),
                ),
            ),
        ),
    )
    return ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )


def test_fundamental_snapshot_uses_latest_frozen_known_at_row() -> None:
    feed = _pit_snapshot_feed()

    result = feed.get_fundamental_snapshot(
        [InstrumentId(1), InstrumentId(2)],
        date(2026, 1, 5),
    )

    assert result.columns == ["instrument_id", "roe", "net_margin", "eps"]
    assert result.rows() == [
        (1, 0.20, 0.09, 1.2),
        (2, 0.30, 0.10, 1.4),
    ]


def test_classification_snapshot_uses_latest_frozen_known_at_row() -> None:
    feed = _pit_snapshot_feed()

    result = feed.get_classification_snapshot(
        [InstrumentId(1), InstrumentId(2)],
        date(2026, 1, 5),
    )

    assert result.columns == ["instrument_id", "sector_id"]
    assert result.rows() == [(1, "bank-new"), (2, "technology")]


def test_pit_snapshot_fails_when_requested_instrument_has_no_known_row() -> None:
    feed = _pit_snapshot_feed()

    with pytest.raises(AppProcessError) as exc_info:
        feed.get_fundamental_snapshot(
            [InstrumentId(1), InstrumentId(3)],
            date(2026, 1, 5),
        )

    assert exc_info.value.details["reason"] == "missing_frozen_pit_row"
    assert exc_info.value.details["instrument_ids"] == [3]


def test_evidence_manifest_exposes_exact_snapshot_hashes_and_sources() -> None:
    frames = _minimal_frames()
    snapshot = _snapshot(frames)
    feed = ResearchDataFeed(
        snapshot=snapshot,
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    manifest = feed.evidence_manifest

    assert manifest.snapshot_id == "research-snapshot-exact-v1"
    assert manifest.snapshot_manifest_hash == "f" * 64
    assert tuple(item.frame_kind for item in manifest.frames) == (
        ResearchFrameKind.BARS,
        ResearchFrameKind.CALENDAR,
        ResearchFrameKind.MEMBERSHIP,
    )
    bars = manifest.frames[0]
    assert bars.input_id == "bars.parquet"
    assert bars.content_hash == frames.bars.verified_content_hash
    assert bars.schema_hash == frames.bars.verified_schema_hash
    assert bars.source_snapshot_ids == (_source_id(ResearchFrameKind.BARS),)
    assert manifest.canonical_hash == feed_module.research_data_feed_manifest_hash(
        snapshot,
    )


@pytest.mark.parametrize(
    "shadow_name",
    ["get_slice", "require_verified_state", "unexpected_runtime_state"],
)
def test_runtime_reverification_rejects_instance_level_state_shadow(
    shadow_name: str,
) -> None:
    frames = _minimal_frames()
    snapshot = _snapshot(frames)
    manifest_hash = feed_module.research_data_feed_manifest_hash(snapshot)
    feed = ResearchDataFeed(
        snapshot=snapshot,
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
        expected_manifest_hash=manifest_hash,
    )
    object.__setattr__(feed, shadow_name, lambda: None)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed.require_verified_state(
            feed,
            expected_snapshot=snapshot,
            expected_start_date="2026-01-02",
            expected_end_date="2026-01-05",
            expected_knowledge_lag_days=0,
            expected_benchmark=None,
            expected_manifest_hash=manifest_hash,
        )

    assert exc_info.value.details["reason"] == "research_data_feed_state_drift"


def test_runtime_reverification_reparses_bytes_and_rejects_cached_frame_drift() -> None:
    frames = _minimal_frames()
    snapshot = _snapshot(frames)
    manifest_hash = feed_module.research_data_feed_manifest_hash(snapshot)
    feed = ResearchDataFeed(
        snapshot=snapshot,
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
        expected_manifest_hash=manifest_hash,
    )
    stored_frames = vars(feed)["_frames"]
    assert type(stored_frames) is FrozenResearchDataFrames
    stored_frames.bars.frame.replace_column(
        stored_frames.bars.frame.get_column_index("close"),
        pl.Series("close", [99.0, 99.0]),
    )

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed.require_verified_state(
            feed,
            expected_snapshot=snapshot,
            expected_start_date="2026-01-02",
            expected_end_date="2026-01-05",
            expected_knowledge_lag_days=0,
            expected_benchmark=None,
            expected_manifest_hash=manifest_hash,
        )

    assert exc_info.value.details["reason"] == "research_data_feed_state_drift"
    assert exc_info.value.details["field"] == "bars.frame"


def test_runtime_reverification_accepts_the_exact_frozen_feed_state() -> None:
    frames = _minimal_frames()
    snapshot = _snapshot(frames)
    manifest_hash = feed_module.research_data_feed_manifest_hash(snapshot)
    feed = ResearchDataFeed(
        snapshot=snapshot,
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
        expected_manifest_hash=manifest_hash,
    )

    ResearchDataFeed.require_verified_state(
        feed,
        expected_snapshot=snapshot,
        expected_start_date="2026-01-02",
        expected_end_date="2026-01-05",
        expected_knowledge_lag_days=0,
        expected_benchmark=None,
        expected_manifest_hash=manifest_hash,
    )


def test_feed_manifest_hash_uses_only_ordered_declared_feed_artifacts() -> None:
    frames = _minimal_frames()
    factor = ContentAddressedResearchInput(
        input_id="factor@1",
        artifact_kind="factor",
        content_hash="8" * 64,
        schema_hash="9" * 64,
    )
    snapshot = _snapshot(frames, extra_inputs=(factor,))
    reordered = replace(
        snapshot,
        inputs=tuple(reversed(snapshot.inputs)),
    )

    assert feed_module.research_data_feed_manifest_hash(snapshot) == (
        feed_module.research_data_feed_manifest_hash(reordered)
    )
    assert feed_module.research_data_feed_manifest_hash(snapshot) == (
        feed_module.research_data_feed_manifest_hash(_snapshot(frames))
    )

    drifted_bars = replace(
        frames.bars.input_evidence,
        content_hash="7" * 64,
    )
    drifted = replace(
        snapshot,
        inputs=tuple(
            drifted_bars if item.artifact_kind == "bars" else item
            for item in snapshot.inputs
        ),
    )
    assert feed_module.research_data_feed_manifest_hash(drifted) != (
        feed_module.research_data_feed_manifest_hash(snapshot)
    )


def test_feed_rejects_expected_manifest_drift_before_execution() -> None:
    frames = _minimal_frames()

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
            expected_manifest_hash="0" * 64,
        )

    assert exc_info.value.details["reason"] == "data_feed_manifest_hash_drift"


def test_configured_benchmark_requires_exact_bar_for_each_execution_session() -> None:
    frames = _minimal_frames()
    mapping, benchmark = _benchmark_binding(frames)
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames, extra_inputs=(mapping,)),
            frames=frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
            benchmark=benchmark,
        )

    assert exc_info.value.details["reason"] == "missing_exact_benchmark_bar"


def test_calendar_accepts_frozen_polars_date_column() -> None:
    frames = _minimal_frames()
    dated_calendar = _verified(
        ResearchFrameKind.CALENDAR,
        frames.calendar.frame.with_columns(
            pl.col("trade_date").str.to_date(),
        ),
    )
    dated_frames = replace(frames, calendar=dated_calendar)
    feed = ResearchDataFeed(
        snapshot=_snapshot(dated_frames),
        frames=dated_frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]


@pytest.mark.parametrize(
    "kind",
    [
        pytest.param(ResearchFrameKind.BARS, id="bars"),
        pytest.param(ResearchFrameKind.CALENDAR, id="calendar"),
        pytest.param(ResearchFrameKind.MEMBERSHIP, id="membership"),
    ],
)
def test_required_frames_reject_duplicate_semantic_keys(
    kind: ResearchFrameKind,
) -> None:
    frames = _minimal_frames()
    original = getattr(frames, kind.value)
    duplicated = _verified(
        kind,
        pl.concat([original.frame, original.frame.head(1)]),
    )
    invalid_frames = replace(frames, **{kind.value: duplicated})

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "duplicate_frozen_frame_key"
    assert exc_info.value.details["frame_kind"] == kind.value


@pytest.mark.parametrize(
    ("start_date", "end_date", "reason"),
    [
        pytest.param(
            "2026/01/02",
            "2026-01-05",
            "invalid_execution_window",
            id="non-iso-start",
        ),
        pytest.param(
            "2026-01-06",
            "2026-01-05",
            "invalid_execution_window",
            id="reversed",
        ),
    ],
)
def test_execution_window_fails_closed(
    start_date: str,
    end_date: str,
    reason: str,
) -> None:
    frames = _minimal_frames()
    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(frames),
            frames=frames,
            start_date=start_date,
            end_date=end_date,
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == reason


def test_execution_window_requires_an_exact_open_session() -> None:
    frames = _minimal_frames()
    closed_calendar = _verified(
        ResearchFrameKind.CALENDAR,
        frames.calendar.frame.with_columns(pl.lit(False).alias("is_open")),
    )
    invalid_frames = replace(frames, calendar=closed_calendar)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "no_frozen_execution_sessions"


def test_malformed_date_value_is_a_typed_reproducibility_failure() -> None:
    frames = _minimal_frames()
    invalid_calendar = _verified(
        ResearchFrameKind.CALENDAR,
        frames.calendar.frame.with_columns(
            pl.when(pl.col("trade_date") == "2026-01-02")
            .then(pl.lit("not-a-date"))
            .otherwise(pl.col("trade_date"))
            .alias("trade_date"),
        ),
    )
    invalid_frames = replace(frames, calendar=invalid_calendar)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "invalid_frozen_date_value"
    assert exc_info.value.details["frame_kind"] == "calendar"


def test_every_execution_session_requires_daily_membership_evidence() -> None:
    frames = _minimal_frames()
    first_day_only = _verified(
        ResearchFrameKind.MEMBERSHIP,
        frames.membership.frame.filter(
            pl.col("trade_date") == "2026-01-02",
        ),
    )
    invalid_frames = replace(frames, membership=first_day_only)

    with pytest.raises(AppProcessError) as exc_info:
        ResearchDataFeed(
            snapshot=_snapshot(invalid_frames),
            frames=invalid_frames,
            start_date="2026-01-02",
            end_date="2026-01-05",
            knowledge_lag_days=0,
        )

    assert exc_info.value.details["reason"] == "missing_exact_membership_session"
    assert exc_info.value.details["trade_dates"] == ["2026-01-05"]


def test_feed_detaches_mutable_frame_state_at_construction() -> None:
    frames = _minimal_frames()
    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    frames.bars.frame.replace_column(
        frames.bars.frame.get_column_index("close"),
        pl.Series("close", [99.0, 99.0]),
    )

    assert feed.get_slice("2026-01-02").bars[InstrumentId(1)].close == 10.0


def test_feed_reparses_artifact_instead_of_trusting_mutated_parsed_frame() -> None:
    frames = _minimal_frames()
    frames.bars.frame.replace_column(
        frames.bars.frame.get_column_index("close"),
        pl.Series("close", [99.0, 99.0]),
    )

    feed = ResearchDataFeed(
        snapshot=_snapshot(frames),
        frames=frames,
        start_date="2026-01-02",
        end_date="2026-01-05",
        knowledge_lag_days=0,
    )

    assert feed.get_slice("2026-01-02").bars[InstrumentId(1)].close == 10.0


def test_adapter_satisfies_existing_data_feed_protocol() -> None:
    feed: DataFeed = _minimal_feed()

    assert feed.trading_days() == ["2026-01-02", "2026-01-05"]


def test_configured_benchmark_is_exposed_but_not_a_strategy_bar() -> None:
    dates = ("2026-01-02", "2026-01-05")
    frames = FrozenResearchDataFrames(
        bars=_verified(
            ResearchFrameKind.BARS,
            _bars(
                (
                    (dates[0], 1, 10.0),
                    (dates[0], 99, 100.0),
                    (dates[1], 1, 11.0),
                    (dates[1], 99, 101.0),
                ),
            ),
        ),
        calendar=_verified(ResearchFrameKind.CALENDAR, _calendar(*dates)),
        membership=_verified(
            ResearchFrameKind.MEMBERSHIP,
            _membership(
                (
                    (dates[0], 1, True),
                    (dates[0], 99, True),
                    (dates[1], 1, True),
                    (dates[1], 99, True),
                ),
            ),
        ),
    )
    mapping, benchmark = _benchmark_binding(frames)
    feed = ResearchDataFeed(
        snapshot=_snapshot(frames, extra_inputs=(mapping,)),
        frames=frames,
        start_date=dates[0],
        end_date=dates[1],
        knowledge_lag_days=0,
        benchmark=benchmark,
    )

    result = feed.get_slice(dates[0])

    assert result.benchmark_close == 100.0
    assert set(result.bars) == {InstrumentId(1)}


def test_research_artifact_hash_helpers_bind_exact_bytes_and_ordered_schema() -> None:
    frame = pl.DataFrame({"a": [1, 2], "b": [1.0, 2.0]})
    artifact_bytes = _parquet_bytes(frame)

    content_hash = feed_module.research_artifact_content_hash(artifact_bytes)
    schema_hash = feed_module.research_frame_schema_hash(frame)

    assert content_hash == hashlib.sha256(artifact_bytes).hexdigest()
    assert content_hash != feed_module.research_artifact_content_hash(
        _parquet_bytes(frame.reverse()),
    )
    assert schema_hash != feed_module.research_frame_schema_hash(
        frame.select("b", "a"),
    )
    assert schema_hash != feed_module.research_frame_schema_hash(
        frame.with_columns(pl.col("a").cast(pl.Int32)),
    )


def test_verified_frame_self_verifies_and_parses_exact_parquet_bytes() -> None:
    frame = _calendar("2026-01-02")
    artifact_bytes = _parquet_bytes(frame)
    evidence = _artifact_input(ResearchFrameKind.CALENDAR, artifact_bytes, frame)

    verified = VerifiedResearchFrame(
        input_evidence=evidence,
        source_snapshot_ids=(_source_id(ResearchFrameKind.CALENDAR),),
        artifact_bytes=artifact_bytes,
    )

    assert verified.frame.equals(frame)
    assert verified.verified_content_hash == evidence.content_hash
    assert verified.verified_schema_hash == evidence.schema_hash
    assert set(signature(VerifiedResearchFrame).parameters) == {
        "input_evidence",
        "source_snapshot_ids",
        "artifact_bytes",
    }
