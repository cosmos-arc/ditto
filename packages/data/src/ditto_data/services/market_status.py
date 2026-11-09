"""Join dated stock facts and retain explicit, non-trading suspension marks."""

import polars as pl


def stock_execution_bars(
    bars: pl.DataFrame,
    status: pl.DataFrame,
    limits: pl.DataFrame,
    *,
    valuation_history: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """
    Carry only a verified past close for a confirmed full-day suspension.

    The original quote date/source remain visible. These valuation rows belong
    only to the execution channel; adjusted signal history reads raw bars.
    """
    keys = ["instrument_id", "trade_date"]
    bars = bars.with_columns(
        pl.col("trade_date").alias("valuation_date"),
        pl.lit(False).alias("is_valuation_only"),
    )
    quotes = (
        pl.concat([bars, valuation_history], how="diagonal_relaxed").with_columns(
            pl.col("trade_date").alias("valuation_date")
        )
        if valuation_history is not None
        else bars
    )
    missing = status.filter(pl.col("is_suspended")).join(
        bars.select(keys), on=keys, how="anti"
    )
    if not missing.is_empty():
        if "suspend_timing" not in missing.columns:
            raise ValueError("missing full-day suspension evidence")
        partial = missing.filter(
            ~pl.col("suspend_timing").fill_null("").is_in(["", "全天", "09:30-15:00"])
        )
        if not partial.is_empty():
            raise ValueError(
                "missing intraday suspension quote: " + str(_locations(partial))
            )
        marks = (
            missing.select(keys)
            .sort("trade_date")
            .join_asof(
                quotes.rename({"trade_date": "_quote_date"}).sort("_quote_date"),
                left_on="trade_date",
                right_on="_quote_date",
                by="instrument_id",
                strategy="backward",
                allow_exact_matches=False,
                check_sortedness=False,
            )
        )
        invalid = marks.filter(
            pl.col("close").is_null()
            | ~pl.col("close").is_finite()
            | (pl.col("close") <= 0)
            | pl.col("source_snapshot_id").is_null()
        )
        if not invalid.is_empty():
            raise ValueError(
                "missing prior suspension valuation: " + str(_locations(invalid))
            )
        marks = marks.with_columns(
            *[
                pl.col("close").alias(column)
                for column in ("open", "high", "low", "pre_close")
            ],
            pl.lit(0.0).alias("volume"),
            pl.lit(0.0).alias("amount"),
            pl.lit(True).alias("is_valuation_only"),
        ).drop("_quote_date")
        bars = pl.concat([bars, marks], how="diagonal_relaxed")
    joined = bars.join(
        status.select(
            *keys,
            "is_suspended",
            "is_st",
            "list_status",
            pl.col("source_snapshot_id").alias("status_source_snapshot_id"),
        ),
        on=keys,
        how="left",
        validate="1:1",
    ).join(
        limits.select(
            *keys,
            pl.col("up_limit").alias("limit_up"),
            pl.col("down_limit").alias("limit_down"),
            pl.col("source_snapshot_id").alias("limit_source_snapshot_id"),
        ),
        on=keys,
        how="left",
        validate="1:1",
    )
    unknown = joined.filter(
        pl.any_horizontal(
            pl.col(column).is_null()
            for column in (
                "is_suspended",
                "is_st",
                "list_status",
                "status_source_snapshot_id",
            )
        )
    )
    if not unknown.is_empty():
        raise ValueError(f"unknown stock status: {_locations(unknown)}")
    invalid_limits = joined.filter(
        ~pl.col("is_suspended")
        & pl.any_horizontal(
            pl.col(column).is_null()
            for column in ("limit_up", "limit_down", "limit_source_snapshot_id")
        )
    )
    if not invalid_limits.is_empty():
        raise ValueError(
            "missing stock price limits: " + str(_locations(invalid_limits))
        )
    if joined.filter(pl.col("list_status") != "L").height:
        raise ValueError("unsupported stock lifecycle state")
    return joined.sort(keys)


def _locations(frame: pl.DataFrame) -> list[dict[str, object]]:
    return (
        frame.select("instrument_id", pl.col("trade_date").cast(pl.String))
        .head(10)
        .to_dicts()
    )
