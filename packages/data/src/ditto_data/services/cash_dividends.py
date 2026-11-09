"""Select source-backed implemented cash distributions without guessing events."""

from datetime import date

import polars as pl

_RATIO_EPSILON = 1e-10


def cash_adjusted_suspension_marks(
    bars: pl.DataFrame, events: tuple[tuple[int, date, float, float], ...]
) -> pl.DataFrame:
    """Deduct known cash rights from carried cum-dividend quotes, never signal bars."""
    for instrument, ex_date, gross, shares in sorted(events, key=lambda e: e[1]):
        applies = (
            pl.col("is_valuation_only")
            & (pl.col("instrument_id") == instrument)
            & (pl.col("valuation_date") < ex_date)
            & (pl.col("trade_date") >= ex_date)
        )
        bars = bars.with_columns(
            pl.when(applies)
            .then((pl.col(column) - gross) / (1 + shares))
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
    """Require independent dates, share ratios and issuer tax evidence."""
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
            "retained dividend lacks implementation/cash/share facts; recollect v4"
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
    if frame.filter(
        pl.col("stock_dividend_ratio").is_null()
        | ~pl.col("stock_dividend_ratio").is_finite()
        | (pl.col("stock_dividend_ratio") < 0)
    ).height:
        raise ValueError("unknown stock distribution ratio")
    facts += _share_facts(frame)
    if frame.filter(
        pl.col("gross_dividend_per_share").is_null()
        | ~pl.col("gross_dividend_per_share").is_finite()
        | (pl.col("gross_dividend_per_share") < 0)
    ).height:
        raise ValueError("unknown gross dividend")
    frame = frame.filter(
        (pl.col("gross_dividend_per_share") > 0) | (pl.col("stock_dividend_ratio") > 0)
    )
    if (
        frame.select("record_date", "implementation_date")
        .null_count()
        .sum_horizontal()
        .sum()
    ):
        raise ValueError("unknown dividend implementation dates")
    if frame.filter(
        (pl.col("gross_dividend_per_share") > 0) & pl.col("pay_date").is_null()
    ).height:
        raise ValueError("unknown dividend implementation dates")
    if (
        frame.select(facts)
        .unique()
        .group_by("instrument_id", "ex_dividend_date")
        .len()
        .filter(pl.col("len") > 1)
        .height
    ):
        raise ValueError("conflicting dividend revisions; reconcile source facts")
    return frame.sort("source_snapshot_id").unique(
        subset=facts, keep="first", maintain_order=True
    )


def _share_facts(frame: pl.DataFrame) -> list[str]:
    """Validate share-only requirements without inventing facts for cash events."""
    shares = frame.filter(pl.col("stock_dividend_ratio") > 0)
    share_facts = [
        "bonus_ratio",
        "capitalization_ratio",
        "share_listing_date",
        "taxable_share_income",
        "share_tax_basis",
        "share_tax_knowledge_date",
    ]
    if shares.height:
        if not set(share_facts).issubset(frame.columns):
            raise ValueError(
                "share accounting requires listing and issuer tax evidence"
            )
        if shares.filter(pl.any_horizontal(pl.col(share_facts).is_null())).height:
            raise ValueError(
                "share accounting requires listing and issuer tax evidence"
            )
        if shares.filter(
            (pl.col("share_listing_date") < pl.col("ex_dividend_date"))
            | (pl.col("share_tax_knowledge_date") >= pl.col("record_date"))
            | (pl.col("share_tax_basis").str.len_chars() == 0)
            | (pl.col("taxable_share_income") < 0)
            | ~pl.col("taxable_share_income").is_finite()
            | (pl.col("bonus_ratio") < 0)
            | ~pl.col("bonus_ratio").is_finite()
            | (pl.col("capitalization_ratio") < 0)
            | ~pl.col("capitalization_ratio").is_finite()
            | (
                (
                    pl.col("bonus_ratio")
                    + pl.col("capitalization_ratio")
                    - pl.col("stock_dividend_ratio")
                ).abs()
                > _RATIO_EPSILON
            )
        ).height:
            raise ValueError("invalid stock distribution listing/ratios/tax evidence")
        return share_facts
    return []
