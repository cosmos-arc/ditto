"""Market-bar normalization for isolated R3 live research snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl

type LiveLane = Literal["stock", "etf"]

_END = date(2026, 7, 31)
_BENCHMARK_INSTRUMENT_ID = 3_000_149
_BAR_KEY = ("trade_date", "instrument_id")


__all__ = [
    "align_live_membership",
    "bar_history_grid",
    "build_live_bars",
    "deduplicate_physical_bars",
    "normalized_bars",
    "scan_market_store",
]


def scan_market_store(
    data_root: Path,
    asset_class: str,
    store: Literal["bars", "adj"],
) -> pl.LazyFrame:
    """
    Scan one market Parquet store (bars or adjustment factors).

    The adjustment store publishes rows on suspension days too, so its join
    with the suspension-carried bar grid is total up to partition seams;
    residual gaps inside one instrument close by forward-fill only.
    """
    names = {
        "bars": "bar",
        "adj": "adjustment factor",
    }
    paths = sorted((data_root / "market" / asset_class / store).glob("*.parquet"))
    if not paths:
        raise ValueError(f"live {asset_class} {names[store]} files are missing")
    return pl.scan_parquet(paths)


def _membership_with_observed_bar_history(
    raw: pl.DataFrame,
    membership: pl.DataFrame,
) -> pl.DataFrame:
    """
    Exclude membership dates that precede an instrument's first known bar.

    A suspension that crosses the retained-data boundary has no prior close that
    can be carried without looking into the future. Once an instrument has one
    observed bar, later gaps remain in the grid and are handled as suspensions.
    """
    requested_ids = {int(item) for item in membership["instrument_id"].unique()}
    observed_ids = {int(item) for item in raw["instrument_id"].unique()}
    missing = sorted(requested_ids - observed_ids)
    if missing:
        rendered = ", ".join(str(item) for item in missing)
        raise ValueError(f"live members have no observed bars: {rendered}")
    first_observed = raw.group_by("instrument_id").agg(
        pl.col("trade_date").min().alias("_first_observed_bar")
    )
    aligned = (
        membership.join(first_observed, on="instrument_id", how="inner")
        .filter(pl.col("trade_date") >= pl.col("_first_observed_bar"))
        .drop("_first_observed_bar")
        .sort(["trade_date", "instrument_id"])
    )
    if aligned.is_empty():
        raise ValueError("live membership has no dates with observed bar history")
    return aligned


def align_live_membership(
    data_root: Path,
    lane: LiveLane,
    membership: pl.DataFrame,
) -> pl.DataFrame:
    """Align a live universe to the retained point-in-time bar boundary."""
    member_ids = membership["instrument_id"].unique().to_list()
    source_class = "stock" if lane == "stock" else "etf"
    raw = (
        scan_market_store(data_root, source_class, "bars")
        .filter(
            (pl.col("trade_date") <= _END) & pl.col("instrument_id").is_in(member_ids)
        )
        .select("trade_date", "instrument_id")
        .collect()
    )
    return _membership_with_observed_bar_history(raw, membership)


def bar_history_grid(
    raw: pl.DataFrame,
    membership: pl.DataFrame,
    sessions: tuple[date, ...],
) -> pl.DataFrame:
    """Retain pre-membership prices needed by later PIT-universe factor lookbacks."""
    instrument_ids = membership.select("instrument_id").unique().sort("instrument_id")
    session_frame = pl.DataFrame(
        {"trade_date": sessions},
        schema={"trade_date": pl.Date},
    )
    requested = session_frame.join(instrument_ids, how="cross").select(
        "trade_date",
        "instrument_id",
    )
    return _membership_with_observed_bar_history(raw, requested)


def deduplicate_physical_bars(
    raw: pl.DataFrame,
    *,
    store: str = "bar",
) -> pl.DataFrame:
    """Collapse identical partition overlap and reject ambiguous market truth."""
    unique_rows = raw.unique(maintain_order=True)
    conflicting_keys = (
        unique_rows.group_by(_BAR_KEY).len().filter(pl.col("len") > 1).sort(_BAR_KEY)
    )
    if not conflicting_keys.is_empty():
        sample = conflicting_keys.select(*_BAR_KEY).head(3)
        raise ValueError(f"conflicting live {store} duplicates: {sample}")
    return unique_rows.sort(_BAR_KEY)


def normalized_bars(
    raw: pl.DataFrame,
    membership: pl.DataFrame,
    *,
    authority_snapshot_id: str,
    adjustment: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """
    Project a complete membership grid with suspension-safe carried prices.

    ``adjustment`` carries ``(trade_date, instrument_id, adj_factor)`` rows for
    every calendar session; ``None`` projects the neutral factor 1.0 used for
    index benchmarks, which have no corporate-action adjustment by contract.
    """
    raw = deduplicate_physical_bars(raw)
    selected = raw.select(
        "trade_date",
        "instrument_id",
        "open",
        "high",
        "low",
        "close",
        pl.col("pre_close").alias("prev_close"),
        "volume",
        "amount",
    )
    requested = membership.select("trade_date", "instrument_id").unique()
    first_dates = requested.group_by("instrument_id").agg(
        pl.col("trade_date").min().alias("_first_trade_date")
    )
    seeds = (
        first_dates.sort(["instrument_id", "_first_trade_date"])
        .join_asof(
            selected.select(
                "instrument_id",
                pl.col("trade_date").alias("_seed_trade_date"),
                pl.col("close").alias("_seed_close"),
            ).sort(["instrument_id", "_seed_trade_date"]),
            left_on="_first_trade_date",
            right_on="_seed_trade_date",
            by="instrument_id",
            strategy="backward",
            allow_exact_matches=False,
        )
        .select("instrument_id", "_seed_close")
    )
    grid = (
        requested.join(
            selected,
            on=["trade_date", "instrument_id"],
            how="left",
        )
        .join(seeds, on="instrument_id", how="left")
        .sort(["instrument_id", "trade_date"])
    )
    if adjustment is not None:
        # Adjustment partitions overlap exactly like bar partitions; collapse
        # identical rows and refuse ambiguous factors before the grid join
        # (a duplicated row would multiply every downstream grid row).
        grid = grid.join(
            deduplicate_physical_bars(
                adjustment.select("trade_date", "instrument_id", "adj_factor"),
                store="adjustment factor",
            ),
            on=["trade_date", "instrument_id"],
            how="left",
        ).sort(["instrument_id", "trade_date"])
        # Joins do not guarantee output order; every forward-fill below is a
        # within-instrument time carry, so re-establish the order explicitly.
        grid = grid.with_columns(
            pl.col("adj_factor").forward_fill().over("instrument_id"),
        )
        if grid["adj_factor"].null_count():
            missing = grid.filter(pl.col("adj_factor").is_null()).select(
                "trade_date", "instrument_id"
            )
            raise ValueError(f"live member has no adjustment factor: {missing.head(3)}")
    grid = grid.with_columns(
        pl.coalesce(
            pl.col("close").forward_fill().over("instrument_id"),
            pl.col("_seed_close"),
        ).alias("_carry_close")
    )
    if grid["_carry_close"].null_count():
        missing = grid.filter(pl.col("_carry_close").is_null()).select(
            "trade_date", "instrument_id"
        )
        raise ValueError(
            f"live member has no prior bar for suspension fill: {missing.head(3)}"
        )
    suspended = pl.col("close").is_null()
    normalized = grid.with_columns(
        suspended.alias("is_suspended"),
        pl.when(suspended)
        .then(pl.col("_carry_close"))
        .otherwise(pl.col("open"))
        .alias("open"),
        pl.when(suspended)
        .then(pl.col("_carry_close"))
        .otherwise(pl.col("high"))
        .alias("high"),
        pl.when(suspended)
        .then(pl.col("_carry_close"))
        .otherwise(pl.col("low"))
        .alias("low"),
        pl.col("_carry_close").alias("close"),
        pl.when(suspended)
        .then(pl.col("_carry_close"))
        .otherwise(pl.col("prev_close"))
        .alias("prev_close"),
        pl.when(suspended).then(0.0).otherwise(pl.col("volume")).alias("volume"),
        pl.when(suspended).then(0.0).otherwise(pl.col("amount")).alias("amount"),
    ).drop("_carry_close", "_seed_close")
    return normalized.with_columns(
        (pl.col("prev_close") * 1.1).round(2).cast(pl.Float64).alias("limit_up"),
        (pl.col("prev_close") * 0.9).round(2).cast(pl.Float64).alias("limit_down"),
        pl.col("volume")
        .rolling_mean(window_size=20, min_samples=1)
        .over("instrument_id")
        .alias("avg_volume_20d"),
        (
            pl.lit(1.0, dtype=pl.Float64)
            if adjustment is None
            else pl.col("adj_factor")
        ).alias("adj_factor"),
        pl.lit(authority_snapshot_id).alias("source_snapshot_id"),
    ).select(
        "trade_date",
        "instrument_id",
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "volume",
        "amount",
        "is_suspended",
        "limit_up",
        "limit_down",
        "avg_volume_20d",
        "adj_factor",
        "source_snapshot_id",
    )


def build_live_bars(
    data_root: Path,
    lane: LiveLane,
    membership: pl.DataFrame,
    sessions: tuple[date, ...],
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    """Load member and benchmark bars through the production Parquet contract."""
    member_ids = membership["instrument_id"].unique().to_list()
    source_class = "stock" if lane == "stock" else "etf"
    raw = (
        scan_market_store(data_root, source_class, "bars")
        .filter(
            (pl.col("trade_date") <= _END) & pl.col("instrument_id").is_in(member_ids)
        )
        .collect()
    )
    adjustment = (
        scan_market_store(data_root, source_class, "adj")
        .filter(
            (pl.col("trade_date") <= _END) & pl.col("instrument_id").is_in(member_ids)
        )
        .select("trade_date", "instrument_id", "adj_factor")
        .collect()
    )
    history_grid = bar_history_grid(raw, membership, sessions)
    member_bars = normalized_bars(
        raw,
        history_grid,
        authority_snapshot_id=authority_snapshot_id,
        adjustment=adjustment,
    )
    benchmark = (
        scan_market_store(data_root, "index", "bars")
        .filter(
            (pl.col("trade_date") <= _END)
            & (pl.col("instrument_id") == _BENCHMARK_INSTRUMENT_ID)
        )
        .collect()
    )
    benchmark_membership = pl.DataFrame(
        {
            "trade_date": sessions,
            "instrument_id": (_BENCHMARK_INSTRUMENT_ID,) * len(sessions),
        },
        schema={"trade_date": pl.Date, "instrument_id": pl.Int64},
    )
    benchmark_bars = normalized_bars(
        benchmark,
        benchmark_membership,
        # Index levels carry no corporate-action adjustment; the neutral
        # factor keeps the one-frame contract total for benchmark rows.
        authority_snapshot_id=authority_snapshot_id,
    )
    return pl.concat((member_bars, benchmark_bars)).sort(
        ["trade_date", "instrument_id"]
    )
