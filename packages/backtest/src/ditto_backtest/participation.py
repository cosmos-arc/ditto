"""Daily candidate eligibility over frozen membership and listing facts."""

from datetime import timedelta

import polars as pl
from ditto_execution.reality.ordinary_equity import MIN_ORDINARY_LISTED_DAYS


def daily_participation(
    roster: list[dict[str, object]],
    days: list[str],
    *,
    warmup_days: int,
    knowledge_lag_days: int,
    ipo_covered_ids: frozenset[int] = frozenset(),
) -> pl.DataFrame:
    """Project half-open membership and listing life; count actual prior sessions."""
    intervals = pl.DataFrame(roster).with_columns(
        pl.col("effective_from", "effective_to", "list_date", "delist_date")
        .cast(pl.String)
        .str.to_date(),
    )
    calendar = pl.Series("trade_date", days).str.to_date().sort()
    grid = intervals.join(calendar.to_frame(), how="cross")
    membership = (pl.col("effective_from") <= pl.col("trade_date")) & (
        pl.col("effective_to").is_null()
        | (pl.col("trade_date") < pl.col("effective_to"))
    )
    grid = (
        grid.with_columns(membership.alias("member"))
        .group_by("instrument_id", "trade_date", "list_date", "delist_date")
        .agg(pl.col("member").any())
    )
    cutoff = grid["trade_date"] - timedelta(days=knowledge_lag_days)
    available = (
        calendar.search_sorted(cutoff).cast(pl.Int64)
        - calendar.search_sorted(grid["list_date"]).cast(pl.Int64)
    ).clip(lower_bound=0)
    grid = grid.with_columns(
        available.alias("warmup_available"),
        pl.lit(warmup_days).alias("warmup_required"),
        (
            (pl.col("list_date") <= pl.col("trade_date"))
            & (
                pl.col("delist_date").is_null()
                | (pl.col("trade_date") < pl.col("delist_date"))
            )
        ).alias("requires_quote"),
    )
    execution_covered = pl.col("instrument_id").is_in(ipo_covered_ids) | (
        (pl.col("trade_date") - pl.col("list_date")).dt.total_days()
        >= MIN_ORDINARY_LISTED_DAYS
    )
    # Other asset cohorts retain their explicit listing-rule limitation.
    return grid.with_columns(
        (pl.col("requires_quote") & execution_covered).alias("execution_available"),
        pl.when(pl.col("trade_date") < pl.col("list_date"))
        .then(pl.lit("not_listed"))
        .when(pl.col("trade_date") >= pl.col("delist_date"))
        .then(pl.lit("delisted"))
        .when(~pl.col("member"))
        .then(pl.lit("outside_universe"))
        .when(pl.col("warmup_available") < warmup_days)
        .then(pl.lit("warmup"))
        .when(~execution_covered)
        .then(pl.lit("listing_rule_unavailable"))
        .otherwise(pl.lit("eligible"))
        .alias("status"),
        pl.col("trade_date").cast(pl.String),
    ).sort("trade_date", "instrument_id")


def apply_market_participation(
    participation: pl.DataFrame,
    execution: pl.DataFrame,
    history: pl.DataFrame,
    *,
    knowledge_lag_days: int,
) -> pl.DataFrame:
    """Exclude known non-trading days and count only real visible observations."""
    visible = (
        history.with_columns(
            pl.max_horizontal(
                pl.col("trade_date").cast(pl.Date) + timedelta(days=1),
                pl.col("knowledge_date").cast(pl.Date),
            ).alias("visible_on")
        )
        .group_by("instrument_id", "visible_on")
        .len()
        .sort("visible_on")
        .with_columns(pl.col("len").cum_sum().over("instrument_id").alias("_available"))
    )
    grid = (
        participation.with_columns(
            (
                pl.col("trade_date").str.to_date() - timedelta(days=knowledge_lag_days)
            ).alias("_cutoff")
        )
        .sort("_cutoff")
        .join_asof(
            visible,
            left_on="_cutoff",
            right_on="visible_on",
            by="instrument_id",
            strategy="backward",
            check_sortedness=False,
        )
        .with_columns(
            pl.col("_available").fill_null(0).cast(pl.Int64).alias("warmup_available")
        )
    )
    facts = execution.select(
        "instrument_id",
        pl.col("trade_date").cast(pl.String),
        "volume",
        pl.col("is_suspended")
        if "is_suspended" in execution.columns
        else pl.lit(False).alias("is_suspended"),
    )
    grid = grid.join(
        facts, on=["instrument_id", "trade_date"], how="left", validate="1:1"
    )
    candidate = pl.col("status").is_in(["eligible", "warmup"])
    return (
        grid.with_columns(
            pl.when(candidate & pl.col("is_suspended"))
            .then(pl.lit("suspended"))
            .when(candidate & (pl.col("volume") == 0))
            .then(pl.lit("zero_volume"))
            .when(candidate & (pl.col("warmup_available") < pl.col("warmup_required")))
            .then(pl.lit("warmup"))
            .when(candidate)
            .then(pl.lit("eligible"))
            .otherwise(pl.col("status"))
            .alias("status")
        )
        .drop("_cutoff", "visible_on", "len", "_available", "volume", "is_suspended")
        .sort("trade_date", "instrument_id")
    )
