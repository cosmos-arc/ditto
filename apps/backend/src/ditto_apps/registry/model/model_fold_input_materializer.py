"""
Production materialization of model-fold frozen input frames (#565 W4).

The real-data adapter behind the model-candidate training port: reads the
stock bar and adjustment-factor Parquet stores through the same
suspension-carrying normalization the frozen research BARS frame uses, then
projects the exact label-price frame contract the forward-return label
builder and the W1 fold orchestration consume. Both frames freeze as
content-addressed research inputs carrying the observed provider snapshot
identities of the partitions they were read from, so a planning request can
pin them before launch and the fold data port re-verifies the bytes at claim
time. Suspension and sell-at-limit-down mirror the backtest fill rule
matrix exactly; the buy side follows the label's own entry-at-next-open
semantics (an open at limit-up is unfillable), which is deliberately
stricter than the engine's close-based buy check (#571 tracks the shared
limit-precision follow-up).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from itertools import pairwise
from pathlib import Path

import orjson
import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.catalog_freshness import observed_snapshot_ids
from ditto_application.processes.experiments._execution_bundle_inputs import (
    ModelFoldInputEvidence,
)
from ditto_application.processes.experiments.model_candidate_folds import (
    ModelFoldInputKind,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    research_artifact_content_hash,
    research_frame_schema_hash,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_features.evaluation.research_labels import LABEL_PRICE_FRAME_SCHEMA

from ditto_apps.config.runtime import state_root_matches
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.live.r3_live_market_projection import (
    bar_history_grid,
    deduplicate_physical_bars,
    normalized_bars,
    scan_market_store,
)
from ditto_apps.registry.live.r3_live_snapshot_frames import open_live_database

__all__ = [
    "MaterializedModelFoldInputs",
    "ModelInputSnapshotSources",
    "build_model_fold_calendar_frame",
    "build_model_fold_label_price_frame",
    "freeze_model_feature_frame",
    "main",
    "materialize_model_fold_inputs",
]

# Model candidates are stock-lane only (W2 lane parity); every dataset read
# here must be observed as a completed provider snapshot before use.
MODEL_INPUT_DATASETS: tuple[str, ...] = ("adj_factor", "calendar", "stock_daily")
_LABEL_PRICE_DATASETS: tuple[str, ...] = ("adj_factor", "stock_daily")

_LABEL_PRICE_COLUMNS: tuple[tuple[str, pl.DataType], ...] = (
    ("instrument_id", pl.String()),
    ("session", pl.Date()),
    ("open", pl.Float64()),
    ("close", pl.Float64()),
    ("adj_factor", pl.Float64()),
    ("buy_fillable_open", pl.Boolean()),
    ("sell_fillable_close", pl.Boolean()),
    ("session_close_known_at_epoch_us", pl.Int64()),
)


def _materializer_error(message: str, **details: object) -> ValueError:
    payload = orjson.dumps(
        {"reason": message, **details}, option=orjson.OPT_SORT_KEYS
    ).decode("utf-8")
    return ValueError(payload)


def _require_window(window_start: date, window_end: date) -> None:
    if type(window_start) is not date or type(window_end) is not date:
        raise _materializer_error("model fold window dates are invalid")
    if window_start > window_end:
        raise _materializer_error(
            "model fold window start is after its end",
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        )


def build_model_fold_calendar_frame(
    connection: sqlite3.Connection,
    *,
    window_start: date,
    window_end: date,
    authority_snapshot_id: str,
) -> tuple[pl.DataFrame, tuple[date, ...]]:
    """Build the complete natural-day calendar inside one fold window."""
    _require_window(window_start, window_end)
    rows = connection.execute(
        """
        SELECT trade_date, is_open
        FROM trading_calendar
        WHERE trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        (window_start.isoformat(), window_end.isoformat()),
    ).fetchall()
    expected_days = (window_end - window_start).days + 1
    if len(rows) != expected_days:
        raise _materializer_error(
            "model fold calendar does not contain every natural day",
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            expected_days=expected_days,
            observed_days=len(rows),
        )
    dates = tuple(date.fromisoformat(str(row["trade_date"])) for row in rows)
    sessions = tuple(
        observed
        for observed, row in zip(dates, rows, strict=True)
        if bool(row["is_open"])
    )
    if not sessions:
        raise _materializer_error("model fold calendar contains no open sessions")
    frame = pl.DataFrame(
        {
            "trade_date": dates,
            "is_open": tuple(bool(row["is_open"]) for row in rows),
            "source_snapshot_id": (authority_snapshot_id,) * len(rows),
        },
        schema={
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
            "source_snapshot_id": pl.String,
        },
    )
    return frame, sessions


def _require_label_price_schema(frame: pl.DataFrame) -> None:
    schema = frame.schema
    for name, dtype in _LABEL_PRICE_COLUMNS:
        if schema.get(name) != dtype:
            raise _materializer_error(
                "model fold label price frame schema is invalid",
                column=name,
                expected=str(dtype),
                observed=str(schema.get(name)),
            )
    if set(schema) != set(LABEL_PRICE_FRAME_SCHEMA):
        raise _materializer_error(
            "model fold label price frame drifted from the label contract",
            expected=sorted(LABEL_PRICE_FRAME_SCHEMA),
            observed=sorted(schema),
        )


def _require_market_session_coverage(
    raw: pl.DataFrame, sessions: tuple[date, ...]
) -> None:
    """
    Fail closed when an open session has no observed market bar at all.

    A fully silent session means a missing partition (or a stale calendar);
    carrying it as suspension would fabricate prices and knowledge.
    """
    uncovered = sorted(set(sessions) - set(raw["trade_date"].to_list()))
    if uncovered:
        raise _materializer_error(
            "model fold sessions have no observed market bars",
            uncovered_sessions=[item.isoformat() for item in uncovered],
        )


def _require_factor_not_published_after_its_bar(
    adjustment_rows: pl.DataFrame,
    raw: pl.DataFrame,
) -> None:
    """
    Fail closed when a factor's publication postdates the bar it scales.

    Real stores publish factors same-day and bars T+1, so a later-published
    restated factor would leak into labels whose declared maturity predates
    it; this pins that invariant instead of expecting it.
    """
    late_factors = adjustment_rows.join(
        raw.select("trade_date", "instrument_id", pl.col("knowledge_date")),
        on=["trade_date", "instrument_id"],
        how="inner",
        suffix="_bar",
    ).filter(pl.col("knowledge_date") > pl.col("knowledge_date_bar"))
    if not late_factors.is_empty():
        raise _materializer_error(
            "model fold adjustment factor published after its bar",
            sample=str(
                late_factors.select("trade_date", "instrument_id", "knowledge_date")
                .head(3)
                .rows()
            ),
        )


def build_model_fold_label_price_frame(
    data_root: Path,
    *,
    instrument_ids: tuple[int, ...],
    sessions: tuple[date, ...],
    authority_snapshot_id: str,
    knowledge_cutoff: date,
) -> pl.DataFrame:
    """
    Project the label-price contract from the real stock bar/adj stores.

    Reuses the frozen BARS normalization (complete session grid, suspension
    carried closes, computed price limits, adjustment factor joined per
    calendar session) so strategy backtests and model labels read one price
    truth. Knowledge times come from the source bars' publication dates; a
    suspension-carried row inherits the carry source's publication date,
    which is exactly when that close value became known. Both stores are read
    strictly as-of ``knowledge_cutoff`` (rows published later are invisible),
    and every requested session must carry at least one real market bar so a
    missing partition fails closed instead of fabricating suspensions.
    """
    root = data_root.expanduser().resolve(strict=True)
    raw_ids = instrument_ids
    if (
        type(raw_ids) is not tuple
        or not raw_ids
        or any(type(item) is not int or item <= 0 for item in raw_ids)
        or len(set(raw_ids)) != len(raw_ids)
    ):
        raise _materializer_error("model fold instrument identities are invalid")
    if (
        type(sessions) is not tuple
        or not sessions
        or any(type(item) is not date for item in sessions)
        or any(current >= following for current, following in pairwise(sessions))
    ):
        raise _materializer_error("model fold sessions are invalid")
    if type(authority_snapshot_id) is not str or not authority_snapshot_id.strip():
        raise _materializer_error("model fold authority snapshot identity is invalid")
    if type(knowledge_cutoff) is not date:
        raise _materializer_error("model fold knowledge cutoff is invalid")
    window_end = sessions[-1]
    member_filter = (
        (pl.col("trade_date") <= window_end)
        & (pl.col("knowledge_date") <= knowledge_cutoff)
        & pl.col("instrument_id").is_in(list(raw_ids))
    )
    # One scan, deduplicated once: the grid, the normalization, and the
    # publication dates all read the same physical bar truth.
    raw = deduplicate_physical_bars(
        scan_market_store(root, "stock", "bars").filter(member_filter).collect()
    )
    _require_market_session_coverage(raw, sessions)
    adjustment_rows = deduplicate_physical_bars(
        scan_market_store(root, "stock", "adj")
        .filter(member_filter)
        .select("trade_date", "instrument_id", "adj_factor", "knowledge_date")
        .collect(),
        store="adjustment factor",
    )
    _require_factor_not_published_after_its_bar(adjustment_rows, raw)
    adjustment = adjustment_rows.select("trade_date", "instrument_id", "adj_factor")
    knowledge = raw.select(
        "trade_date",
        "instrument_id",
        pl.col("knowledge_date").alias("_knowledge_date"),
    )
    membership = pl.DataFrame(
        {
            "trade_date": (sessions[0],) * len(raw_ids),
            "instrument_id": list(raw_ids),
        },
        schema={"trade_date": pl.Date, "instrument_id": pl.Int64},
    )
    history_grid = bar_history_grid(raw, membership, sessions)
    normalized = normalized_bars(
        raw,
        history_grid,
        authority_snapshot_id=authority_snapshot_id,
        adjustment=adjustment,
    )
    # Publication dates exist only on real bar rows; a suspension-carried row
    # inherits the last real bar's publication date through a backward as-of
    # join, which is exactly when the carried close value became known.
    knowledge_grid = (
        normalized.select("trade_date", "instrument_id")
        .sort(["instrument_id", "trade_date"])
        .join_asof(
            knowledge.sort(["instrument_id", "trade_date"]),
            on="trade_date",
            by="instrument_id",
            strategy="backward",
        )
    )
    if knowledge_grid["_knowledge_date"].null_count():
        missing = knowledge_grid.filter(pl.col("_knowledge_date").is_null()).select(
            "trade_date", "instrument_id"
        )
        raise _materializer_error(
            "model fold member has no knowledge date for price publication",
            sample=str(missing.head(3).rows()),
        )
    priced = normalized.join(
        knowledge_grid.select("trade_date", "instrument_id", "_knowledge_date"),
        on=["trade_date", "instrument_id"],
        how="left",
    )
    frame = priced.select(
        pl.col("instrument_id").cast(pl.String).alias("instrument_id"),
        pl.col("trade_date").alias("session"),
        pl.col("open").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("adj_factor").cast(pl.Float64),
        (~pl.col("is_suspended") & (pl.col("open") < pl.col("limit_up"))).alias(
            "buy_fillable_open"
        ),
        (~pl.col("is_suspended") & (pl.col("close") > pl.col("limit_down"))).alias(
            "sell_fillable_close"
        ),
        pl.col("_knowledge_date")
        .cast(pl.Datetime("us"))
        .dt.replace_time_zone("UTC")
        .dt.epoch("us")
        .cast(pl.Int64)
        .alias("session_close_known_at_epoch_us"),
    ).sort(["session", "instrument_id"])
    _require_label_price_schema(frame)
    if frame.is_empty():
        raise _materializer_error("model fold label price frame is empty")
    if frame.select("instrument_id", "session").is_duplicated().any():
        raise _materializer_error("model fold label price frame has duplicate keys")
    if frame.get_column("session_close_known_at_epoch_us").null_count():
        raise _materializer_error("model fold label price frame has missing knowledge")
    non_positive = frame.filter(
        (pl.col("open") <= 0.0)
        | (pl.col("close") <= 0.0)
        | (pl.col("adj_factor") <= 0.0)
    )
    if not non_positive.is_empty():
        raise _materializer_error(
            "model fold label price frame has non-positive prices",
            sample=str(non_positive.head(3).rows()),
        )
    return frame


def _parquet(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer, compression="zstd", statistics=True)
    return buffer.getvalue()


def _model_input_evidence(
    input_kind: ModelFoldInputKind,
    frame: pl.DataFrame,
    *,
    source_snapshot_ids: tuple[str, ...],
) -> tuple[ModelFoldInputEvidence, bytes]:
    payload = _parquet(frame)
    content_hash = research_artifact_content_hash(payload)
    evidence = ModelFoldInputEvidence(
        input_kind=input_kind.value,
        input_id=f"model-input-stock-{input_kind.value}@sha256:{content_hash}",
        content_hash=content_hash,
        schema_hash=research_frame_schema_hash(frame),
        source_snapshot_ids=source_snapshot_ids,
    )
    return evidence, payload


def freeze_model_feature_frame(
    frame: pl.DataFrame,
    *,
    source_snapshot_ids: tuple[str, ...],
    artifact_service: ResearchArtifactService,
) -> ModelFoldInputEvidence:
    """
    Freeze one caller-computed feature frame as the features fold input.

    Feature values are lineage-defined (the model's feature schema and the
    factor chain own their computation); this seam only content-addresses and
    publishes the exact bytes the fold data port will re-verify at claim.
    """
    if type(frame) is not pl.DataFrame or frame.is_empty():
        raise _materializer_error("model fold feature frame is invalid")
    evidence, payload = _model_input_evidence(
        ModelFoldInputKind.FEATURES,
        frame,
        source_snapshot_ids=source_snapshot_ids,
    )
    artifact_service.publish_frozen_research_input(evidence.input_id, payload)
    return evidence


@dataclass(frozen=True, slots=True)
class MaterializedModelFoldInputs:
    """Published fold-input identities one planning request can pin."""

    label_prices: ModelFoldInputEvidence
    calendar: ModelFoldInputEvidence
    sessions: tuple[date, ...]
    authority_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelInputSnapshotSources:
    """Observed provider snapshot resolution ports, always resolved together."""

    snapshot_reader: ProviderSnapshotReader
    lifecycle_reader: PartitionLifecycleReader


def _observed_snapshots(
    sources: ModelInputSnapshotSources,
    *,
    dataset_id: str,
    observed_cutoff: datetime,
    window_start: date,
    window_end: date,
) -> tuple[tuple[ProviderSnapshot, ...], tuple[str, ...]]:
    snapshot_ids = observed_snapshot_ids(
        sources.snapshot_reader,
        sources.lifecycle_reader,
        dataset_ids=(dataset_id,),
        knowledge_cutoff=observed_cutoff,
    )
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in snapshot_ids:
        snapshot = sources.snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.dataset_id != dataset_id:
            raise _materializer_error(
                "observed model input snapshot is missing or mismatched",
                dataset_id=dataset_id,
                snapshot_id=snapshot_id,
            )
        snapshots.append(snapshot)
    if not snapshots:
        raise _materializer_error(
            "no completed observed snapshots cover the model fold window",
            dataset_id=dataset_id,
        )
    covered_from = min(date.fromisoformat(item.request_start) for item in snapshots)
    covered_through = max(date.fromisoformat(item.request_end) for item in snapshots)
    if covered_from > window_start or covered_through < window_end:
        raise _materializer_error(
            "observed model input snapshots do not span the fold window",
            dataset_id=dataset_id,
            covered_from=covered_from.isoformat(),
            covered_through=covered_through.isoformat(),
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        )
    return tuple(snapshots), snapshot_ids


def materialize_model_fold_inputs(
    *,
    data_root: Path,
    artifact_service: ResearchArtifactService,
    sources: ModelInputSnapshotSources,
    instrument_ids: tuple[int, ...],
    window_start: date,
    window_end: date,
    observed_cutoff: datetime | None = None,
) -> MaterializedModelFoldInputs:
    """Freeze the label-price and calendar fold inputs from real data."""
    _require_window(window_start, window_end)
    if observed_cutoff is not None and observed_cutoff.tzinfo is None:
        # A naive cutoff would silently bind to the machine timezone and
        # shift snapshot visibility; require the caller to be explicit.
        raise _materializer_error("model fold observed cutoff must be tz-aware")
    cutoff = (
        observed_cutoff.astimezone(UTC)
        if observed_cutoff is not None
        else datetime.now(UTC)
    )
    by_dataset = {
        dataset_id: _observed_snapshots(
            sources,
            dataset_id=dataset_id,
            observed_cutoff=cutoff,
            window_start=window_start,
            window_end=window_end,
        )
        for dataset_id in MODEL_INPUT_DATASETS
    }
    authority_candidates = tuple(
        snapshot
        for snapshot in by_dataset["stock_daily"][0]
        if date.fromisoformat(snapshot.request_start)
        <= window_end
        <= date.fromisoformat(snapshot.request_end)
    )
    if not authority_candidates:
        raise _materializer_error(
            "stock daily provider evidence does not span the fold window end",
            window_end=window_end.isoformat(),
        )
    authority = max(
        authority_candidates,
        key=lambda item: (
            item.request_end,
            item.request_start,
            item.snapshot_id.encode(),
        ),
    )
    root = data_root.expanduser().resolve(strict=True)
    connection = open_live_database(root)
    try:
        calendar_frame, sessions = build_model_fold_calendar_frame(
            connection,
            window_start=window_start,
            window_end=window_end,
            authority_snapshot_id=authority.snapshot_id,
        )
    finally:
        connection.close()
    label_frame = build_model_fold_label_price_frame(
        root,
        instrument_ids=instrument_ids,
        sessions=sessions,
        authority_snapshot_id=authority.snapshot_id,
        knowledge_cutoff=cutoff.date(),
    )
    label_sources = tuple(
        sorted(
            {
                snapshot_id
                for dataset_id in _LABEL_PRICE_DATASETS
                for snapshot_id in by_dataset[dataset_id][1]
            }
        )
    )
    calendar_sources = by_dataset["calendar"][1]
    label_evidence, label_payload = _model_input_evidence(
        ModelFoldInputKind.LABEL_PRICES,
        label_frame,
        source_snapshot_ids=label_sources,
    )
    calendar_evidence, calendar_payload = _model_input_evidence(
        ModelFoldInputKind.CALENDAR,
        calendar_frame,
        source_snapshot_ids=calendar_sources,
    )
    artifact_service.publish_frozen_research_input(
        label_evidence.input_id, label_payload
    )
    artifact_service.publish_frozen_research_input(
        calendar_evidence.input_id, calendar_payload
    )
    return MaterializedModelFoldInputs(
        label_prices=label_evidence,
        calendar=calendar_evidence,
        sessions=sessions,
        authority_snapshot_id=authority.snapshot_id,
        source_snapshot_ids=tuple(
            sorted(
                {snapshot_id for pair in by_dataset.values() for snapshot_id in pair[1]}
            )
        ),
    )


def _parse_instruments(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for token in raw.split(","):
        text = token.strip()
        if (
            not text.isascii()
            or not text.isdecimal()
            or (len(text) > 1 and text.startswith("0"))
        ):
            raise SystemExit(f"instrument identity is not canonical: {text!r}")
        ids.append(int(text))
    if not ids:
        raise SystemExit("at least one instrument identity is required")
    if len(set(ids)) != len(ids):
        raise SystemExit("instrument identities must be unique")
    return tuple(ids)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--instruments", help="Comma-separated canonical ids")
    parser.add_argument(
        "--instruments-file",
        type=Path,
        help="File with one canonical instrument id per line",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Compose production ports and print the frozen fold-input evidence."""
    args = _parser().parse_args(argv)
    data_root = args.data_root.expanduser().resolve(strict=True)
    if not state_root_matches(data_root):
        raise SystemExit("DITTO_STATE_ROOT must exactly match --data-root")
    if (args.instruments is None) == (args.instruments_file is None):
        raise SystemExit("exactly one of --instruments or --instruments-file")
    if args.instruments is not None:
        instrument_ids = _parse_instruments(args.instruments)
    else:
        text = (
            args.instruments_file.expanduser()
            .resolve(strict=True)
            .read_text(encoding="utf-8")
        )
        entries = tuple(line.strip() for line in text.splitlines() if line.strip())
        if not entries:
            raise SystemExit("instruments file is empty")
        instrument_ids = _parse_instruments(",".join(entries))
    container = make_app_container()
    try:
        result = materialize_model_fold_inputs(
            data_root=data_root,
            artifact_service=container.get(ResearchArtifactService),
            sources=ModelInputSnapshotSources(
                snapshot_reader=container.get(ProviderSnapshotReader),
                lifecycle_reader=container.get(PartitionLifecycleReader),
            ),
            instrument_ids=instrument_ids,
            window_start=args.start,
            window_end=args.end,
        )
    finally:
        container.close()
    sys.stdout.write(
        orjson.dumps(
            {
                "authority_snapshot_id": result.authority_snapshot_id,
                "calendar": dict(result.calendar.as_payload()),
                "label_prices": dict(result.label_prices.as_payload()),
                "sessions": [item.isoformat() for item in result.sessions],
                "source_snapshot_ids": list(result.source_snapshot_ids),
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode("utf-8")
        + "\n",
    )
    return 0
