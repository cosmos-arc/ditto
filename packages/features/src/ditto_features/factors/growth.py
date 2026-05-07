"""Growth factor definitions — revenue and earnings growth."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

__all__ = ["GROWTHS"]

GROWTHS: dict[str, FactorSpec] = {
    "revenue_growth": FactorSpec(
        id="revenue_growth",
        expression="ts_pct_change(fundamentals.revenue, 4)",
        dependencies=("fundamentals.revenue",),
        description="Year-over-year revenue growth (4-quarter change)",
    ),
    "net_profit_growth": FactorSpec(
        id="net_profit_growth",
        expression="ts_pct_change(fundamentals.net_income, 4)",
        dependencies=("fundamentals.net_income",),
        description="Year-over-year net profit growth (4-quarter change)",
    ),
    "op_profit_growth": FactorSpec(
        id="op_profit_growth",
        expression="ts_pct_change(fundamentals.op_income, 4)",
        dependencies=("fundamentals.op_income",),
        description="Year-over-year operating profit growth (4-quarter change)",
    ),
    "growth_stability": FactorSpec(
        id="growth_stability",
        expression="ts_corr(revenue_growth, net_profit_growth, 8)",
        dependencies=("revenue_growth", "net_profit_growth"),
        description="Revenue-profit growth correlation over 8 quarters",
    ),
    "sustainable_growth": FactorSpec(
        id="sustainable_growth",
        expression="",
        dependencies=("roe",),
        description="Sustainable growth rate: ROE * (1 - dividend payout ratio)",
        computation_type="python",
    ),
}
