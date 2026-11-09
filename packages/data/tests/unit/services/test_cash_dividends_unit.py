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
    result = cash_adjusted_suspension_marks(bars, ((1, date(2020, 6, 3), 1, 0),))
    assert result["close"].to_list() == [10, 9, 9]
    assert result["valuation_date"].to_list() == bars["valuation_date"].to_list()


def test_implemented_shares_require_listing_and_matched_issuer_tax_evidence():
    from ditto_data.config.data_source import DataSourceSettings, StockDistributionTerms
    from ditto_data.sources.stock_distribution_terms import (
        bind_stock_distribution_terms,
    )

    frame = pl.DataFrame(
        {
            "instrument_id": [1],
            "source_ticker": ["600000.SH"],
            "source_snapshot_id": ["source:shares"],
            "div_proc": ["实施"],
            "record_date": [date(2020, 6, 2)],
            "ex_dividend_date": [date(2020, 6, 3)],
            "pay_date": [None],
            "implementation_date": [date(2020, 5, 28)],
            "gross_dividend_per_share": [0.0],
            "stock_dividend_ratio": [0.5],
            "bonus_ratio": [0.0],
            "capitalization_ratio": [0.5],
            "share_listing_date": [date(2020, 6, 5)],
        }
    ).with_columns(pl.col("pay_date").cast(pl.Date))
    term = StockDistributionTerms.model_validate(
        {
            "source_ticker": "600000.SH",
            "record_date": "2020-06-02",
            "ex_date": "2020-06-03",
            "listing_date": "2020-06-05",
            "bonus_ratio": 0,
            "capitalization_ratio": 0.5,
            "taxable_share_income": 0,
            "announcement_date": "2020-05-28",
            "basis_url": "https://issuer.example/announcement",
        }
    )
    bound = bind_stock_distribution_terms(frame, (term,))
    settings = DataSourceSettings.model_validate(
        {"stock_distribution_terms": f"[{term.model_dump_json()}]"}
    )
    assert settings.stock_distribution_terms == (term,)
    assert (
        implemented_cash_dividends(bound, start="2020-06-01", end="2020-06-10").height
        == 1
    )
    with pytest.raises(ValueError, match="tax evidence"):
        implemented_cash_dividends(
            bind_stock_distribution_terms(frame, ()),
            start="2020-06-01",
            end="2020-06-10",
        )
    with pytest.raises(ValueError, match="conflicts"):
        bind_stock_distribution_terms(
            frame.with_columns(pl.lit(date(2020, 6, 8)).alias("share_listing_date")),
            (term,),
        )
    missing_bonus = frame.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("bonus_ratio")
    )
    assert bind_stock_distribution_terms(missing_bonus, (term,))[
        "bonus_ratio"
    ].to_list() == [0]
    compound = frame.with_columns(
        pl.lit(0.1).alias("bonus_ratio"),
        pl.lit(0.2).alias("capitalization_ratio"),
        pl.lit(0.3).alias("stock_dividend_ratio"),
    )
    compound_term = term.model_copy(
        update={
            "bonus_ratio": 0.1,
            "capitalization_ratio": 0.2,
            "taxable_share_income": 0.1,
        }
    )
    assert bind_stock_distribution_terms(compound, (compound_term,)).height == 1
    with pytest.raises(ValueError, match="late"):
        bind_stock_distribution_terms(
            frame, (term.model_copy(update={"announcement_date": date(2020, 6, 3)}),)
        )
