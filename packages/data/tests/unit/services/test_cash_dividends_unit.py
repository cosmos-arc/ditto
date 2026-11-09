"""Retained implementation facts, ambiguity and carried suspension marks."""

from datetime import date

import polars as pl
import pytest
from ditto_data.services.cash_dividends import (
    cash_adjusted_suspension_marks,
    implemented_cash_dividends,
)


def test_duplicate_cash_events_collapse_but_revision_and_missing_facts_block():
    frame = pl.DataFrame(
        {
            "instrument_id": [1],
            "source_snapshot_id": ["source:1"],
            "div_proc": ["实施"],
            "record_date": [date(2020, 6, 2)],
            "ex_dividend_date": [date(2020, 6, 3)],
            "pay_date": [date(2020, 6, 5)],
            "implementation_date": [date(2020, 5, 28)],
            "gross_dividend_per_share": [1.0],
            "stock_dividend_ratio": [0.0],
        }
    )

    def select(rows):
        return implemented_cash_dividends(rows, start="2020-06-01", end="2020-06-05")

    assert select(pl.concat([frame, frame])).height == 1
    with pytest.raises(ValueError, match="conflicting dividend revisions"):
        select(
            pl.concat(
                [
                    frame,
                    frame.with_columns(pl.lit(2.0).alias("gross_dividend_per_share")),
                ]
            )
        )
    with pytest.raises(ValueError, match="implementation dates"):
        select(frame.with_columns(pl.lit(None, dtype=pl.Date).alias("pay_date")))
    with pytest.raises(ValueError, match="share accounting"):
        select(frame.with_columns(pl.lit(0.1).alias("stock_dividend_ratio")))


@pytest.mark.pit
def test_suspended_quote_is_adjusted_only_from_the_confirmed_ex_date():
    bars = pl.DataFrame(
        {
            "instrument_id": [1, 1, 1],
            "trade_date": [date(2020, 6, day) for day in (2, 3, 4)],
            "valuation_date": [date(2020, 6, 1)] * 3,
            "is_valuation_only": [True] * 3,
            **{
                field: [10.0] * 3
                for field in ("open", "high", "low", "close", "pre_close")
            },
        }
    )
    result = cash_adjusted_suspension_marks(bars, ((1, date(2020, 6, 3), 1),))
    assert result["close"].to_list() == [10, 9, 9]
    assert result["valuation_date"].to_list() == bars["valuation_date"].to_list()
