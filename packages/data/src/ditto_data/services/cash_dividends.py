"""Select source-backed implemented cash distributions without guessing events."""

from datetime import date

import polars as pl


def cash_adjusted_suspension_marks(
    bars: pl.DataFrame, events: tuple[tuple[int, date, float], ...]
) -> pl.DataFrame:
    """Deduct known cash rights from carried cum-dividend quotes, never signal bars."""
    for instrument, ex_date, gross in events:
        applies = (
            pl.col("is_valuation_only")
            & (pl.col("instrument_id") == instrument)
            & (pl.col("valuation_date") < ex_date)
            & (pl.col("trade_date") >= ex_date)
        )
        bars = bars.with_columns(
            pl.when(applies)
            .then(pl.col(column) - gross)
            .otherwise(pl.col(column))
            .alias(column)
            for column in ("open", "high", "low", "close", "pre_close")
        )
    if bars.filter(pl.col("close") <= 0).height:
        raise ValueError("cash dividend exceeds retained suspension valuation")
    return bars


def implemented_cash_dividends(
    frame: pl.DataFrame, *, start: str, end: str
) -> pl.DataFrame:
    """Reject ambiguous revisions and share distributions in the cash-only scope."""
    facts = [
        "instrument_id",
        "div_proc",
        "record_date",
        "ex_dividend_date",
        "pay_date",
        "implementation_date",
        "gross_dividend_per_share",
        "stock_dividend_ratio",
    ]
    if not set(facts).issubset(frame.columns):
        raise ValueError(
            "retained dividend lacks implementation/cash/share facts; recollect v3"
        )
    frame = frame.filter(pl.col("div_proc") == "实施")
    if frame["ex_dividend_date"].null_count():
        raise ValueError("implemented dividend lacks ex date")
    frame = frame.filter(
        (pl.col("ex_dividend_date") >= date.fromisoformat(start))
        & (
            (pl.col("record_date") <= date.fromisoformat(end))
            | (pl.col("ex_dividend_date") <= date.fromisoformat(end))
        )
    )
    if (
        frame.select(facts)
        .unique()
        .group_by("instrument_id", "ex_dividend_date")
        .len()
        .filter(pl.col("len") > 1)
        .height
    ):
        raise ValueError("conflicting dividend revisions; reconcile source facts")
    if frame.filter(
        pl.col("stock_dividend_ratio").is_null() | (pl.col("stock_dividend_ratio") != 0)
    ).height:
        raise ValueError("stock distribution requires share accounting")
    if frame.filter(
        pl.col("gross_dividend_per_share").is_null()
        | ~pl.col("gross_dividend_per_share").is_finite()
        | (pl.col("gross_dividend_per_share") < 0)
    ).height:
        raise ValueError("unknown gross dividend")
    frame = frame.filter(pl.col("gross_dividend_per_share") > 0)
    if (
        frame.select("record_date", "pay_date", "implementation_date")
        .null_count()
        .sum_horizontal()
        .sum()
    ):
        raise ValueError("unknown dividend implementation dates")
    return frame.sort("source_snapshot_id").unique(
        subset=facts, keep="first", maintain_order=True
    )
