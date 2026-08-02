"""Market-bar normalization for isolated R3 live research snapshots."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl

type LiveLane = Literal["stock", "etf"]

_END = date(2026, 7, 31)
_BENCHMARK_INSTRUMENT_ID = 3_000_149


def _scan_bars(data_root: Path, asset_class: str) -> pl.LazyFrame:
    paths = sorted((data_root / "market" / asset_class / "bars").glob("*.parquet"))
    if not paths:
        raise ValueError(f"live {asset_class} bar files are missing")
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
        _scan_bars(data_root, source_class)
        .filter(
            (pl.col("trade_date") <= _END) & pl.col("instrument_id").is_in(member_ids)
        )
        .select("trade_date", "instrument_id")
        .collect()
    )
    return _membership_with_observed_bar_history(raw, membership)


def _normalized_bars(
    raw: pl.DataFrame,
    membership: pl.DataFrame,
    *,
    authority_snapshot_id: str,
) -> pl.DataFrame:
    """Project a complete membership grid with suspension-safe carried prices."""
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
        _scan_bars(data_root, source_class)
        .filter(
            (pl.col("trade_date") <= _END) & pl.col("instrument_id").is_in(member_ids)
        )
        .collect()
    )
    member_bars = _normalized_bars(
        raw,
        membership,
        authority_snapshot_id=authority_snapshot_id,
    )
    benchmark = (
        _scan_bars(data_root, "index")
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
    benchmark_bars = _normalized_bars(
        benchmark,
        benchmark_membership,
        authority_snapshot_id=authority_snapshot_id,
    )
    return pl.concat((member_bars, benchmark_bars)).sort(
        ["trade_date", "instrument_id"]
    )
