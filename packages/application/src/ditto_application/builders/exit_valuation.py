"""Exit-held valuation notes for delisted members of a frozen stock run."""

from __future__ import annotations

import polars as pl

__all__ = ["exit_held_valuation_notes"]


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
    delisting cash accounting is evidenced on this path.

    Returns one ``(instrument_id, trade_date, _exit_note)`` row per delisted
    stock participation day; the anchor sentence is omitted when no retained
    quote exists for the instrument at all.
    """
    exits = {
        int(str(row["instrument_id"])): str(row["delist_date"])
        for row in roster
        if row.get("delist_date") and str(row.get("asset_class", "")) == "stock"
    }
    delisted = participation.filter(
        (pl.col("status") == "delisted") & pl.col("instrument_id").is_in(exits)
    )
    if delisted.is_empty():
        return delisted.select(
            "instrument_id", "trade_date", pl.lit("").alias("_exit_note")
        ).clear()
    if not execution_bars.is_empty() and {
        "is_valuation_only",
        "valuation_date",
    }.issubset(execution_bars.columns):
        anchors = (
            execution_bars.filter(pl.col("instrument_id").is_in(exits))
            .sort("trade_date")
            .group_by("instrument_id")
            .last()
            .select(
                "instrument_id",
                pl.col("close"),
                pl.when(pl.col("is_valuation_only"))
                .then(pl.col("valuation_date"))
                .otherwise(pl.col("trade_date"))
                .alias("_anchor_date"),
            )
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
            .replace_strict(exits, return_dtype=pl.String)
            .alias("_delist_date")
        )
        .join(anchors, on="instrument_id", how="left")
        .with_columns(
            pl.concat_str(
                pl.lit(" · 已退出上市 "),
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
                pl.lit("; 无退市清算会计证据"),
            ).alias("_exit_note")
        )
        .select("instrument_id", "trade_date", "_exit_note")
    )
