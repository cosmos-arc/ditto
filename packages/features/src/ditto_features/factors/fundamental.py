"""Fundamental indicator factor definitions."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

__all__ = ["FUNDAMENTALS"]

FUNDAMENTALS: dict[str, FactorSpec] = {
    "pe_ratio": FactorSpec(
        id="pe_ratio",
        expression="market.close / fundamentals.earnings_per_share",
        dependencies=("market.close", "fundamentals.earnings_per_share"),
        description="Price-to-Earnings ratio",
    ),
    "pb_ratio": FactorSpec(
        id="pb_ratio",
        expression="market.close / fundamentals.book_value_per_share",
        dependencies=("market.close", "fundamentals.book_value_per_share"),
        description="Price-to-Book ratio",
    ),
    "ps_ratio": FactorSpec(
        id="ps_ratio",
        expression="market.close / fundamentals.revenue_per_share",
        dependencies=("market.close", "fundamentals.revenue_per_share"),
        description="Price-to-Sales ratio",
    ),
    "debt_ratio": FactorSpec(
        id="debt_ratio",
        expression="fundamentals.total_debt / fundamentals.total_assets",
        dependencies=("fundamentals.total_debt", "fundamentals.total_assets"),
        description="Debt-to-Asset ratio",
    ),
    "roe": FactorSpec(
        id="roe",
        expression="fundamentals.net_income / fundamentals.equity",
        dependencies=("fundamentals.net_income", "fundamentals.equity"),
        description="Return on Equity",
    ),
    "net_margin": FactorSpec(
        id="net_margin",
        expression="fundamentals.net_income / fundamentals.revenue",
        dependencies=("fundamentals.net_income", "fundamentals.revenue"),
        description="Net Profit Margin",
    ),
    "asset_turnover": FactorSpec(
        id="asset_turnover",
        expression="fundamentals.revenue / fundamentals.total_assets",
        dependencies=("fundamentals.revenue", "fundamentals.total_assets"),
        description="Asset Turnover ratio",
    ),
    "earnings_growth": FactorSpec(
        id="earnings_growth",
        expression="ts_pct_change(fundamentals.earnings_per_share, 4)",
        dependencies=("fundamentals.earnings_per_share",),
        description="4-quarter earnings growth rate",
    ),
}
