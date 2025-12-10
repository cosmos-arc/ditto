"""Pandera schemas for market data validation."""

import pandera.pandas as pa
from pandera.typing import DataFrame, Series


class DailyPriceSchema(pa.DataFrameModel):
    """Pandera schema for daily price data validation."""

    symbol: Series[str] = pa.Field(
        str_matches=r"^\d{6}\.(SH|SZ)$", description="ETF symbol with exchange suffix"
    )
    trade_date: Series[str] = pa.Field(
        str_matches=r"^\d{8}$", description="Trade date in YYYYMMDD format"
    )
    open_price: Series[float] = pa.Field(ge=0, description="Opening price")
    high_price: Series[float] = pa.Field(ge=0, description="Highest price")
    low_price: Series[float] = pa.Field(ge=0, description="Lowest price")
    close_price: Series[float] = pa.Field(ge=0, description="Closing price")
    volume: Series[int] = pa.Field(ge=0, description="Trading volume in shares")
    amount: Series[float] = pa.Field(ge=0, description="Trading amount in currency")
    knowledge_date: Series[str] = pa.Field(
        str_matches=r"^\d{8}$", description="Knowledge date for PIT safety"
    )

    @pa.check("open_price")
    def price_consistency(self, open_price: Series[float]) -> Series[bool]:
        """Check that prices are consistent with each other."""
        return True  # Additional consistency checks can be added here

    @pa.dataframe_check
    def high_low_relationship(self, df: DataFrame) -> bool:
        """Check that high >= max(open, close) and low <= min(open, close)."""
        return all(
            (df["high_price"] >= df[["open_price", "close_price"]].max(axis=1))
            & (df["low_price"] <= df[["open_price", "close_price"]].min(axis=1))
        )


class AdjustmentFactorSchema(pa.DataFrameModel):
    """Pandera schema for adjustment factor data validation."""

    symbol: Series[str] = pa.Field(
        str_matches=r"^\d{6}\.(SH|SZ)$", description="ETF symbol with exchange suffix"
    )
    ex_date: Series[str] = pa.Field(
        str_matches=r"^\d{8}$", description="Ex-dividend date in YYYYMMDD format"
    )
    adj_factor: Series[float] = pa.Field(gt=0, description="Adjustment factor")
    adj_type: Series[str] = pa.Field(
        isin=["cumulative", "point"], description="Adjustment type"
    )
    knowledge_date: Series[str] = pa.Field(
        str_matches=r"^\d{8}$", description="Knowledge date for PIT safety"
    )

    @pa.dataframe_check
    def cumulative_factor_monotonic(self, df: DataFrame) -> bool | None:
        """Check that cumulative adjustment factors are monotonic for each symbol."""
        # Only check for cumulative factors
        cumulative_df = df[df["adj_type"] == "cumulative"]
        if cumulative_df.empty:
            return True

        # For each symbol, check that factors are non-decreasing over time
        for symbol in cumulative_df["symbol"].unique():
            symbol_df = cumulative_df[cumulative_df["symbol"] == symbol].sort_values(
                "ex_date"
            )
            if not symbol_df["adj_factor"].is_monotonic_increasing:
                return False
        return True
