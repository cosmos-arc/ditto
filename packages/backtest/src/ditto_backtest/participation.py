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
    # IPO execution rules remain unqualified in this ordinary rule cohort.
    # Retain the interval and its explicit reason instead of deleting the security.
    return grid.with_columns(
        (
            pl.col("requires_quote")
            & (
                (pl.col("trade_date") - pl.col("list_date")).dt.total_days()
                >= MIN_ORDINARY_LISTED_DAYS
            )
        ).alias("execution_available"),
        pl.when(pl.col("trade_date") < pl.col("list_date"))
        .then(pl.lit("not_listed"))
        .when(pl.col("trade_date") >= pl.col("delist_date"))
        .then(pl.lit("delisted"))
        .when(~pl.col("member"))
        .then(pl.lit("outside_universe"))
        .when(pl.col("warmup_available") < warmup_days)
        .then(pl.lit("warmup"))
        .when(
            (pl.col("trade_date") - pl.col("list_date")).dt.total_days()
            < MIN_ORDINARY_LISTED_DAYS
        )
        .then(pl.lit("listing_rule_unavailable"))
        .otherwise(pl.lit("eligible"))
        .alias("status"),
        pl.col("trade_date").cast(pl.String),
    ).sort("trade_date", "instrument_id")
