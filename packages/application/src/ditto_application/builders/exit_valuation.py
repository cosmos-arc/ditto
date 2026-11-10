"""
Exit-held valuation notes for delisted members of a frozen run.

Stocks exit by delisting (退出上市); ETFs exit by termination of listing
(终止上市). Both keep the held position at the last verified quote and both
share one authoritative note builder — only the asset-class term differs.
"""

from __future__ import annotations

import polars as pl

__all__ = ["exit_held_valuation_notes"]

_EXIT_TERMS = {
    "stock": ("已退出上市", "无退市清算会计证据"),
    "etf": ("已终止上市", "无终止上市清算会计证据"),
}


def exit_held_valuation_notes(
    participation: pl.DataFrame,
    roster: list[dict[str, object]],
    execution_bars: pl.DataFrame,
) -> pl.DataFrame:
    """
    Explain delisted participation days from the frozen exit fact.

    The roster's ``delist_date`` is the request's frozen exit fact. After it a
    held position is retained at the last verified execution quote; the note
    names that anchor (its own quote date and close) so the carried valuation
    is traceable. It never claims a liquidation, a sale or a settlement — no
    delisting/termination cash accounting is evidenced on this path.

    Returns one ``(instrument_id, trade_date, _exit_note)`` row per delisted
    stock/ETF participation day; the anchor sentence is omitted when no
    retained quote exists for the instrument at all. ETF bars carry no
    suspension-valuation columns, so their anchor date is the quote day.
    """
    exits = {
        int(str(row["instrument_id"])): (str(row["delist_date"]), term)
        for row in roster
        if row.get("delist_date")
        and (term := _EXIT_TERMS.get(str(row.get("asset_class", "")))) is not None
    }
    delisted = participation.filter(
        (pl.col("status") == "delisted") & pl.col("instrument_id").is_in(exits)
    )
    if delisted.is_empty():
        return delisted.select(
            "instrument_id", "trade_date", pl.lit("").alias("_exit_note")
        ).clear()
    if not execution_bars.is_empty():
        last_quote = (
            execution_bars.filter(pl.col("instrument_id").is_in(exits))
            .sort("trade_date")
            .group_by("instrument_id")
            .last()
        )
        if {"is_valuation_only", "valuation_date"}.issubset(last_quote.columns):
            anchor_date = (
                pl.when(pl.col("is_valuation_only"))
                .then(pl.col("valuation_date"))
                .otherwise(pl.col("trade_date"))
            )
        else:
            anchor_date = pl.col("trade_date")
        anchors = last_quote.select(
            "instrument_id",
            "close",
            anchor_date.alias("_anchor_date"),
        )
    else:
        anchors = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "close": pl.Float64,
                "_anchor_date": pl.Date,
            }
        )
    return (
        delisted.with_columns(
            pl.col("instrument_id")
            .replace_strict(
                {iid: day for iid, (day, _) in exits.items()},
                return_dtype=pl.String,
            )
            .alias("_delist_date"),
            pl.col("instrument_id")
            .replace_strict(
                {iid: term[0] for iid, (_, term) in exits.items()},
                return_dtype=pl.String,
            )
            .alias("_exit_term"),
            pl.col("instrument_id")
            .replace_strict(
                {iid: term[1] for iid, (_, term) in exits.items()},
                return_dtype=pl.String,
            )
            .alias("_no_liquidation_term"),
        )
        .join(anchors, on="instrument_id", how="left")
        .with_columns(
            pl.concat_str(
                pl.lit(" · "),
                pl.col("_exit_term"),
                pl.lit(" "),
                pl.col("_delist_date"),
                pl.lit("; 持仓保留"),
                pl.when(pl.col("close").is_null())
                .then(pl.lit(""))
                .otherwise(
                    pl.concat_str(
                        pl.lit(", 估值锚定 "),
                        pl.col("_anchor_date").cast(pl.String),
                        pl.lit(" 收盘 "),
                        pl.col("close"),
                        pl.lit(" 元"),
                    )
                ),
                pl.lit("; "),
                pl.col("_no_liquidation_term"),
            ).alias("_exit_note")
        )
        .select("instrument_id", "trade_date", "_exit_note")
    )
