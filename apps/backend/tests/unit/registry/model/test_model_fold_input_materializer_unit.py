"""Golden tests for the real-data model-fold input materializer (#565 W4).

The fixtures under ``fixtures/model_fold_inputs`` are exact extracts of the
real 2024 stock bar, adjustment-factor, and trading-calendar stores for three
instruments chosen to exercise the projection's semantics: 1000001 trades
every session, 1005674 suspends mid-window and stops trading 2024-08-05, and
1005790 stops trading 2024-05-15 (its adjustment factor keeps publishing and
every window row is a suspension carry). Pinned literals below come from
those real rows; they anchor the adapter to the stores it reads.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.builders.research_model_fold_adapters import (
    IndexedModelFoldDataPort,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelFoldInputBinding,
    ModelFoldInputEvidence,
    ModelFoldInputKind,
    ModelFoldInputSet,
)
from ditto_apps.registry.model.model_fold_input_materializer import (
    ModelInputSnapshotSources,
    build_model_fold_calendar_frame,
    build_model_fold_label_price_frame,
    freeze_model_feature_frame,
    materialize_model_fold_inputs,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import (
    PartitionLifecycleReader,
    PartitionLifecycleStatus,
)
from ditto_features.evaluation.research_labels import (
    LABEL_STATUS_MATURE,
    LABEL_STATUS_UNFILLABLE_ENTRY,
    build_forward_return_labels,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "model_fold_inputs"
_INSTRUMENTS = (1000001, 1005674, 1005790)
_WINDOW_START = date(2024, 6, 3)
_WINDOW_END = date(2024, 8, 30)
# 2024-06-04 and 2024-05-16 at UTC midnight, in epoch microseconds: the
# publication times of the first window session and the last real bar of the
# fully suspended member.
_KNOWLEDGE_T_PLUS_ONE = 1_717_459_200_000_000
_KNOWLEDGE_CARRY_SOURCE = 1_715_817_600_000_000


def _golden_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    for store in ("bars", "adj"):
        target = root / "market" / "stock" / store
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy(_FIXTURES / f"{store}_2024.parquet", target / "2024.parquet")
    return root


def _calendar_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    frame = pl.read_parquet(_FIXTURES / "calendar_2024.parquet")
    connection.execute(
        "CREATE TABLE trading_calendar (trade_date TEXT, is_open INTEGER)"
    )
    connection.executemany(
        "INSERT INTO trading_calendar VALUES (?, ?)",
        cast("list[tuple[object, ...]]", frame.rows()),
    )
    return connection


def _golden_sessions() -> tuple[date, ...]:
    connection = _calendar_connection()
    try:
        _, sessions = build_model_fold_calendar_frame(
            connection,
            window_start=_WINDOW_START,
            window_end=_WINDOW_END,
            authority_snapshot_id="snapshot-authority",
        )
    finally:
        connection.close()
    return sessions


_KNOWLEDGE_CUTOFF = date(2024, 12, 31)


def _golden_label_frame(tmp_path: Path) -> pl.DataFrame:
    return build_model_fold_label_price_frame(
        _golden_data_root(tmp_path),
        instrument_ids=_INSTRUMENTS,
        sessions=_golden_sessions(),
        authority_snapshot_id="snapshot-authority",
        knowledge_cutoff=_KNOWLEDGE_CUTOFF,
    )


@pytest.mark.unit
def test_calendar_frame_covers_every_natural_day_of_the_window() -> None:
    connection = _calendar_connection()
    try:
        frame, sessions = build_model_fold_calendar_frame(
            connection,
            window_start=_WINDOW_START,
            window_end=_WINDOW_END,
            authority_snapshot_id="snapshot-authority",
        )
    finally:
        connection.close()

    assert frame.height == (_WINDOW_END - _WINDOW_START).days + 1
    assert frame.schema == {
        "trade_date": pl.Date,
        "is_open": pl.Boolean,
        "source_snapshot_id": pl.String,
    }
    assert len(sessions) == 64
    assert sessions[0] == date(2024, 6, 3)
    assert sessions[-1] == date(2024, 8, 30)


@pytest.mark.unit
def test_calendar_frame_rejects_a_window_with_missing_natural_days() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE trading_calendar (trade_date TEXT, is_open INTEGER)"
    )
    connection.executemany(
        "INSERT INTO trading_calendar VALUES (?, ?)",
        [("2024-06-03", 1), ("2024-06-05", 1)],
    )

    with pytest.raises(ValueError, match="every natural day"):
        build_model_fold_calendar_frame(
            connection,
            window_start=date(2024, 6, 3),
            window_end=date(2024, 6, 5),
            authority_snapshot_id="snapshot-authority",
        )


@pytest.mark.unit
def test_label_price_golden_frame_pins_real_projection_values(tmp_path) -> None:
    frame = _golden_label_frame(tmp_path)

    assert frame.schema == {
        "instrument_id": pl.String,
        "session": pl.Date,
        "open": pl.Float64,
        "close": pl.Float64,
        "adj_factor": pl.Float64,
        "buy_fillable_open": pl.Boolean,
        "sell_fillable_close": pl.Boolean,
        "session_close_known_at_epoch_us": pl.Int64,
    }
    # The complete session grid: every member appears on every window session.
    assert frame.height == 192
    assert frame.group_by("instrument_id").len().sort("instrument_id")[
        "len"
    ].to_list() == [
        64,
        64,
        64,
    ]
    assert frame.select("instrument_id", "session").is_duplicated().any() is False

    # A real trading row keeps its exact source prices, factor, and T+1
    # publication time (source bar 2024-06-03: open 11.12 close 10.98).
    first = frame.filter(
        (pl.col("instrument_id") == "1000001") & (pl.col("session") == date(2024, 6, 3))
    ).row(0, named=True)
    assert first["open"] == pytest.approx(11.12)
    assert first["close"] == pytest.approx(10.98)
    assert first["adj_factor"] == pytest.approx(116.713)
    assert first["buy_fillable_open"] is True
    assert first["sell_fillable_close"] is True
    assert first["session_close_known_at_epoch_us"] == _KNOWLEDGE_T_PLUS_ONE

    # The fully suspended member carries the last real bar's close knowledge
    # (2024-05-16) on every window session, keeps its still-published factor
    # (37.477), and is unfillable on both sides.
    suspended = frame.filter(pl.col("instrument_id") == "1005790")
    assert suspended["session_close_known_at_epoch_us"].unique().to_list() == [
        _KNOWLEDGE_CARRY_SOURCE
    ]
    assert suspended["adj_factor"].unique().to_list() == pytest.approx([37.477])
    assert suspended["buy_fillable_open"].any() is False
    assert suspended["sell_fillable_close"].any() is False

    # The mid-window suspension: trading until 2024-08-05, unfillable after.
    partial = (
        frame.filter(pl.col("instrument_id") == "1005674")
        .sort("session")
        .select("session", "buy_fillable_open")
    )
    assert partial.head(1).row(0) == (date(2024, 6, 3), True)
    assert partial.filter(pl.col("session") == date(2024, 8, 5)).row(0) == (
        date(2024, 8, 5),
        True,
    )
    assert partial.tail(1).row(0) == (date(2024, 8, 30), False)


@pytest.mark.unit
def test_label_price_golden_frame_feeds_real_forward_return_labels(tmp_path) -> None:
    frame = _golden_label_frame(tmp_path)
    sessions = _golden_sessions()

    labels = build_forward_return_labels(frame, sessions)

    status = labels.frame.group_by("status").len().sort("status")
    assert dict(status.iter_rows()) == {
        "mature": 81,
        "unfillable_entry": 84,
        "unfillable_exit": 12,
    }

    # One mature label recomputed by hand from the golden frame rows: entry at
    # the next session's open, exit at the fifth held session's close, scaled
    # by the adjustment factors of those two sessions.
    def _row(instrument: str, session: date) -> dict[str, float]:
        row = frame.filter(
            (pl.col("instrument_id") == instrument) & (pl.col("session") == session)
        ).row(0, named=True)
        return cast(
            "dict[str, float]",
            {
                name: value
                for name, value in row.items()
                if name in ("open", "close", "adj_factor")
            },
        )

    decision = sessions[0]
    entry = _row("1000001", sessions[1])
    exit_ = _row("1000001", sessions[5])
    expected = (exit_["close"] * exit_["adj_factor"]) / (
        entry["open"] * entry["adj_factor"]
    ) - 1.0
    mature = labels.frame.filter(
        (pl.col("instrument_id") == "1000001")
        & (pl.col("decision_session") == decision)
        & (pl.col("status") == LABEL_STATUS_MATURE)
    )
    assert mature.height == 1
    assert mature["label_value"].item() == pytest.approx(expected)
    assert mature["entry_session"].item() == sessions[1]
    assert mature["exit_session"].item() == sessions[5]
    # The suspended member contributes only unfillable entries, never a value.
    suspended = labels.frame.filter(pl.col("instrument_id") == "1005790")
    assert suspended.height > 0
    assert (
        suspended.filter(pl.col("status") != LABEL_STATUS_UNFILLABLE_ENTRY).height == 0
    )
    assert suspended["label_value"].null_count() == suspended.height


@pytest.mark.unit
def test_label_price_frame_rejects_member_without_adjustment_factor(tmp_path) -> None:
    root = _golden_data_root(tmp_path)
    adj_path = root / "market" / "stock" / "adj" / "2024.parquet"
    adj = pl.read_parquet(adj_path).filter(pl.col("instrument_id") != 1005790)
    adj.write_parquet(adj_path)

    with pytest.raises(ValueError, match="no adjustment factor"):
        build_model_fold_label_price_frame(
            root,
            instrument_ids=_INSTRUMENTS,
            sessions=_golden_sessions(),
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )


@pytest.mark.unit
def test_label_price_frame_rejects_non_monotonic_sessions(tmp_path) -> None:
    sessions = _golden_sessions()
    broken = (*sessions[:-1], sessions[-2])

    with pytest.raises(ValueError, match="sessions are invalid"):
        build_model_fold_label_price_frame(
            _golden_data_root(tmp_path),
            instrument_ids=_INSTRUMENTS,
            sessions=broken,
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )


@pytest.mark.unit
def test_label_price_frame_fails_closed_on_a_middle_partition_gap(tmp_path) -> None:
    """A missing store month must refuse, not fabricate suspension carries."""
    root = _golden_data_root(tmp_path)
    bars_path = root / "market" / "stock" / "bars" / "2024.parquet"
    july_free = pl.read_parquet(bars_path).filter(pl.col("trade_date").dt.month() != 7)
    july_free.write_parquet(bars_path)

    with pytest.raises(ValueError) as exc_info:
        build_model_fold_label_price_frame(
            root,
            instrument_ids=_INSTRUMENTS,
            sessions=_golden_sessions(),
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )
    details = orjson.loads(str(exc_info.value))
    assert details["reason"] == "model fold sessions have no observed market bars"
    assert len(details["uncovered_sessions"]) == 23
    assert details["uncovered_sessions"][0] == "2024-07-01"


@pytest.mark.unit
def test_label_price_frame_collapses_identical_adjustment_overlap(tmp_path) -> None:
    """Identical partition overlap collapses; conflicting factors refuse."""
    root = _golden_data_root(tmp_path)
    adj_path = root / "market" / "stock" / "adj" / "2024.parquet"
    adj = pl.read_parquet(adj_path)
    pl.concat((adj, adj)).write_parquet(adj_path)
    frame = build_model_fold_label_price_frame(
        root,
        instrument_ids=_INSTRUMENTS,
        sessions=_golden_sessions(),
        authority_snapshot_id="snapshot-authority",
        knowledge_cutoff=_KNOWLEDGE_CUTOFF,
    )
    assert frame.height == 192
    assert frame.select("instrument_id", "session").is_duplicated().any() is False

    conflicting = pl.concat(
        (
            adj,
            adj.with_columns(pl.col("adj_factor") + 1.0).head(1),
        )
    )
    conflicting.write_parquet(adj_path)
    with pytest.raises(ValueError, match="conflicting live adjustment factor"):
        build_model_fold_label_price_frame(
            root,
            instrument_ids=_INSTRUMENTS,
            sessions=_golden_sessions(),
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )


@pytest.mark.unit
def test_label_price_frame_excludes_rows_published_after_the_cutoff(tmp_path) -> None:
    """As-of cutoff: a row published later is invisible; its session fails
    closed as an uncovered market day instead of fabricating a carry."""
    root = _golden_data_root(tmp_path)
    bars_path = root / "market" / "stock" / "bars" / "2024.parquet"
    bars = pl.read_parquet(bars_path).with_columns(
        pl.when(pl.col("trade_date") == date(2024, 7, 1))
        .then(pl.lit(date(2026, 1, 1)).cast(pl.Date))
        .otherwise(pl.col("knowledge_date"))
        .alias("knowledge_date")
    )
    bars.write_parquet(bars_path)

    with pytest.raises(ValueError) as exc_info:
        build_model_fold_label_price_frame(
            root,
            instrument_ids=_INSTRUMENTS,
            sessions=_golden_sessions(),
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )
    details = orjson.loads(str(exc_info.value))
    assert details["reason"] == "model fold sessions have no observed market bars"
    assert details["uncovered_sessions"] == ["2024-07-01"]


@pytest.mark.unit
def test_label_price_frame_rejects_factor_published_after_its_bar(tmp_path) -> None:
    root = _golden_data_root(tmp_path)
    adj_path = root / "market" / "stock" / "adj" / "2024.parquet"
    adj = pl.read_parquet(adj_path).with_columns(
        pl.when(pl.col("trade_date") == date(2024, 6, 3))
        .then(pl.lit(date(2024, 6, 10)).cast(pl.Date))
        .otherwise(pl.col("knowledge_date"))
        .alias("knowledge_date")
    )
    adj.write_parquet(adj_path)

    with pytest.raises(ValueError) as exc_info:
        build_model_fold_label_price_frame(
            root,
            instrument_ids=_INSTRUMENTS,
            sessions=_golden_sessions(),
            authority_snapshot_id="snapshot-authority",
            knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        )
    details = orjson.loads(str(exc_info.value))
    assert details["reason"] == "model fold adjustment factor published after its bar"


@pytest.mark.unit
def test_materialize_rejects_a_naive_observed_cutoff(tmp_path) -> None:
    root = _golden_data_root(tmp_path)
    book = _SnapshotBook()

    with pytest.raises(ValueError, match="must be tz-aware"):
        materialize_model_fold_inputs(
            data_root=root,
            artifact_service=_artifact_service(tmp_path),
            sources=ModelInputSnapshotSources(
                snapshot_reader=cast("ProviderSnapshotReader", book),
                lifecycle_reader=cast("PartitionLifecycleReader", book),
            ),
            instrument_ids=_INSTRUMENTS,
            window_start=_WINDOW_START,
            window_end=_WINDOW_END,
            observed_cutoff=datetime(2026, 10, 2, 12, 0, 0),
        )


class _SnapshotBook:
    """Reader/lifecycle fakes exposing one completed snapshot per dataset."""

    def __init__(self, *, covered_end: str = "2024-12-31") -> None:
        self._snapshots = {
            dataset_id: SimpleNamespace(
                snapshot_id=f"{dataset_id}-current",
                dataset_id=dataset_id,
                source="tushare",
                request_start="2014-01-01",
                request_end=covered_end,
                checksum=f"checksum-{dataset_id}",
                payload_retained=True,
                payload_uri=f"artifact://{dataset_id}",
                created_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
            for dataset_id in ("adj_factor", "calendar", "stock_daily")
        }

    def list_snapshots(self, *, dataset_id: str) -> tuple[SimpleNamespace, ...]:
        item = self._snapshots.get(dataset_id)
        return () if item is None else (item,)

    def get_snapshot(self, snapshot_id: str) -> SimpleNamespace | None:
        return next(
            (
                item
                for item in self._snapshots.values()
                if item.snapshot_id == snapshot_id
            ),
            None,
        )

    def list_complete(self, *, dataset_id: str) -> tuple[SimpleNamespace, ...]:
        item = self._snapshots.get(dataset_id)
        return () if item is None else (self._completion(item),)

    @staticmethod
    def _completion(item: SimpleNamespace) -> SimpleNamespace:
        return SimpleNamespace(
            dataset_id=item.dataset_id,
            source=item.source,
            request_start=item.request_start,
            request_end=item.request_end,
            status=PartitionLifecycleStatus.COMPLETE,
            chunk_id=f"chunk-{item.snapshot_id}",
            payload_id=f"payload:{item.checksum}:synthetic:{item.snapshot_id}",
            complete_evidence_id=item.snapshot_id,
        )


def _artifact_service(tmp_path: Path) -> ResearchArtifactService:
    return ResearchArtifactService(artifact_root=tmp_path / "artifacts")


@pytest.mark.unit
def test_materialize_publishes_inputs_the_fold_port_reads_back(tmp_path) -> None:
    root = _golden_data_root(tmp_path)
    (root / "metadata").mkdir()
    calendar = pl.read_parquet(_FIXTURES / "calendar_2024.parquet")
    disk = sqlite3.connect(root / "metadata" / "metadata.sqlite")
    disk.execute("CREATE TABLE trading_calendar (trade_date TEXT, is_open INTEGER)")
    disk.executemany(
        "INSERT INTO trading_calendar VALUES (?, ?)",
        cast("list[tuple[object, ...]]", calendar.rows()),
    )
    disk.commit()
    disk.close()
    book = _SnapshotBook()
    service = _artifact_service(tmp_path)

    result = materialize_model_fold_inputs(
        data_root=root,
        artifact_service=service,
        sources=ModelInputSnapshotSources(
            snapshot_reader=cast("ProviderSnapshotReader", book),
            lifecycle_reader=cast("PartitionLifecycleReader", book),
        ),
        instrument_ids=_INSTRUMENTS,
        window_start=_WINDOW_START,
        window_end=_WINDOW_END,
        observed_cutoff=datetime(2026, 10, 2, tzinfo=UTC),
    )

    assert result.authority_snapshot_id == "stock_daily-current"
    assert result.sessions == _golden_sessions()
    assert result.source_snapshot_ids == (
        "adj_factor-current",
        "calendar-current",
        "stock_daily-current",
    )
    assert result.label_prices.input_kind == "label_prices"
    assert result.calendar.input_kind == "calendar"
    assert result.label_prices.source_snapshot_ids == (
        "adj_factor-current",
        "stock_daily-current",
    )
    assert result.calendar.source_snapshot_ids == ("calendar-current",)
    for evidence in (result.label_prices, result.calendar):
        assert evidence.input_id == (
            f"model-input-stock-{evidence.input_kind}@sha256:{evidence.content_hash}"
        )

    # The production fold data port re-verifies and loads exactly the bytes
    # the materializer froze; the label frame survives the round trip and the
    # sessions come back in order. The feature frame rides the same store
    # through the caller-supplied freeze seam.
    sessions = _golden_sessions()
    feature_frame = pl.DataFrame(
        {
            "instrument_id": ["1000001"] * len(sessions),
            "session": list(sessions),
            "momentum_20d": [0.1] * len(sessions),
        },
        schema={
            "instrument_id": pl.String,
            "session": pl.Date,
            "momentum_20d": pl.Float64,
        },
    )
    feature_evidence = freeze_model_feature_frame(
        feature_frame,
        source_snapshot_ids=("stock_daily-current",),
        artifact_service=service,
    )
    port = IndexedModelFoldDataPort(artifact_service=service)
    data = port.load(
        ModelFoldInputSet(
            label_prices=_binding(result.label_prices),
            feature_frame=_binding(feature_evidence),
            calendar=_binding(result.calendar),
        )
    )
    assert data.label_prices.equals(_golden_label_frame(tmp_path))
    assert data.feature_frame.equals(feature_frame)
    assert data.trading_sessions == _golden_sessions()
    republished = materialize_model_fold_inputs(
        data_root=root,
        artifact_service=service,
        sources=ModelInputSnapshotSources(
            snapshot_reader=cast("ProviderSnapshotReader", book),
            lifecycle_reader=cast("PartitionLifecycleReader", book),
        ),
        instrument_ids=_INSTRUMENTS,
        window_start=_WINDOW_START,
        window_end=_WINDOW_END,
        observed_cutoff=datetime(2026, 10, 2, tzinfo=UTC),
    )
    assert republished == result


def _binding(evidence: ModelFoldInputEvidence) -> ModelFoldInputBinding:
    return ModelFoldInputBinding(
        kind=ModelFoldInputKind(evidence.input_kind),
        input_id=evidence.input_id,
        content_hash=evidence.content_hash,
        schema_hash=evidence.schema_hash,
        source_snapshot_ids=tuple(evidence.source_snapshot_ids),
    )


@pytest.mark.unit
def test_materialize_rejects_snapshots_that_do_not_span_the_window(tmp_path) -> None:
    root = _golden_data_root(tmp_path)
    book = _SnapshotBook(covered_end="2024-06-30")

    with pytest.raises(ValueError) as exc_info:
        materialize_model_fold_inputs(
            data_root=root,
            artifact_service=_artifact_service(tmp_path),
            sources=ModelInputSnapshotSources(
                snapshot_reader=cast("ProviderSnapshotReader", book),
                lifecycle_reader=cast("PartitionLifecycleReader", book),
            ),
            instrument_ids=_INSTRUMENTS,
            window_start=_WINDOW_START,
            window_end=_WINDOW_END,
            observed_cutoff=datetime(2026, 10, 2, tzinfo=UTC),
        )
    details = orjson.loads(str(exc_info.value))
    assert (
        details["reason"]
        == "observed model input snapshots do not span the fold window"
    )
    assert details["covered_through"] == "2024-06-30"


@pytest.mark.unit
def test_freeze_model_feature_frame_content_addresses_caller_frame(tmp_path) -> None:
    service = _artifact_service(tmp_path)
    frame = pl.DataFrame(
        {
            "instrument_id": ["1000001", "1000001"],
            "session": [date(2024, 6, 3), date(2024, 6, 4)],
            "momentum_20d": [0.1, 0.2],
        },
        schema={
            "instrument_id": pl.String,
            "session": pl.Date,
            "momentum_20d": pl.Float64,
        },
    )

    evidence = freeze_model_feature_frame(
        frame,
        source_snapshot_ids=("stock_daily-current",),
        artifact_service=service,
    )

    assert evidence.input_kind == "features"
    assert evidence.input_id.endswith(evidence.content_hash)
    payload = service.read_frozen_research_input_bytes(evidence.input_id)
    assert hashlib.sha256(payload).hexdigest() == evidence.content_hash
    assert pl.read_parquet(BytesIO(payload)).equals(frame)

    with pytest.raises(ValueError, match="feature frame is invalid"):
        freeze_model_feature_frame(
            frame.head(0),
            source_snapshot_ids=("stock_daily-current",),
            artifact_service=service,
        )


@pytest.mark.unit
def test_cli_instrument_parsing_accepts_only_canonical_identities() -> None:
    from ditto_apps.registry.model.model_fold_input_materializer import (
        _parse_instruments,
    )

    assert _parse_instruments("1000001, 1005674") == (1000001, 1005674)
    with pytest.raises(SystemExit):
        _parse_instruments(chr(0xFF11) + chr(0xFF10) * 5 + chr(0xFF11))
    with pytest.raises(SystemExit):
        _parse_instruments("000001")
    with pytest.raises(SystemExit):
        _parse_instruments("1000001,1000001")
