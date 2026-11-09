"""Bind issuer tax evidence without relabelling it as a vendor-provided fact."""

from datetime import date
from decimal import Decimal

import polars as pl

from ditto_data.config.data_source import StockDistributionTerms


def bind_stock_distribution_terms(
    frame: pl.DataFrame, terms: tuple[StockDistributionTerms, ...]
) -> pl.DataFrame:
    """Retain exact issuer declarations alongside vendor dates and share ratios."""
    if not terms:
        return frame.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("taxable_share_income"),
            pl.lit(None, dtype=pl.String).alias("share_tax_basis"),
            pl.lit(None, dtype=pl.Date).alias("share_tax_knowledge_date"),
        )
    declarations: dict[tuple[str, object], StockDistributionTerms] = {}
    for term in terms:
        key = (term.source_ticker, term.record_date)
        previous = declarations.setdefault(key, term)
        if (
            previous != term
            or term.announcement_date >= term.record_date
            or (term.bonus_ratio > 0 and term.taxable_share_income == 0)
        ):
            raise ValueError("conflicting/late stock distribution tax evidence")
    bonus: list[float | None] = []
    capitalization: list[float | None] = []
    listing: list[date | None] = []
    income: list[float | None] = []
    basis: list[str | None] = []
    knowledge: list[date | None] = []
    for row in frame.iter_rows(named=True):
        term = declarations.get((row["source_ticker"], row["record_date"]))
        if term is not None and row["div_proc"] == "实施":
            expected = (
                term.ex_date,
                term.listing_date,
                term.bonus_ratio,
                term.capitalization_ratio,
            )
            actual = tuple(
                row[key]
                for key in (
                    "ex_dividend_date",
                    "share_listing_date",
                    "bonus_ratio",
                    "capitalization_ratio",
                )
            )
            total = Decimal(str(term.bonus_ratio)) + Decimal(
                str(term.capitalization_ratio)
            )
            if (
                any(
                    a is not None and a != e
                    for a, e in zip(actual, expected, strict=True)
                )
                or row["stock_dividend_ratio"] is None
                or Decimal(str(row["stock_dividend_ratio"])) != total
            ):
                raise ValueError(
                    "issuer tax evidence conflicts with implemented distribution"
                )
            bonus.append(term.bonus_ratio)
            capitalization.append(term.capitalization_ratio)
            listing.append(term.listing_date)
            income.append(term.taxable_share_income)
            basis.append(term.model_dump_json())
            knowledge.append(term.announcement_date)
        else:
            bonus.append(row["bonus_ratio"])
            capitalization.append(row["capitalization_ratio"])
            listing.append(row["share_listing_date"])
            income.append(None)
            basis.append(None)
            knowledge.append(None)
    return frame.with_columns(
        pl.Series("bonus_ratio", bonus, dtype=pl.Float64),
        pl.Series("capitalization_ratio", capitalization, dtype=pl.Float64),
        pl.Series("share_listing_date", listing, dtype=pl.Date),
        pl.Series("taxable_share_income", income, dtype=pl.Float64),
        pl.Series("share_tax_basis", basis, dtype=pl.String),
        pl.Series("share_tax_knowledge_date", knowledge, dtype=pl.Date),
    )
