"""Value factor definitions — valuation ratios and yields."""

from __future__ import annotations

from ditto_analytics.factors.spec import FactorSpec

__all__ = ["VALUES"]

VALUES: dict[str, FactorSpec] = {
    "value_ps": FactorSpec(
        id="value_ps",
        expression="market.close / fundamentals.rvps",
        dependencies=("market.close", "fundamentals.rvps"),
        description="Inverse Price-to-Sales ratio (close / revenue per share)",
    ),
    "value_pcf": FactorSpec(
        id="value_pcf",
        expression=("market.close * fundamentals.total_shares / fundamentals.ocf_ttm"),
        dependencies=(
            "market.close",
            "fundamentals.total_shares",
            "fundamentals.ocf_ttm",
        ),
        description="Inverse Price-to-Cash-Flow ratio",
    ),
    "value_evebitda": FactorSpec(
        id="value_evebitda",
        expression=(
            "(market.close * fundamentals.total_shares "
            "+ fundamentals.total_debt - fundamentals.cash) "
            "/ fundamentals.ebitda"
        ),
        dependencies=(
            "market.close",
            "fundamentals.total_shares",
            "fundamentals.total_debt",
            "fundamentals.cash",
            "fundamentals.ebitda",
        ),
        description="Inverse EV/EBITDA ratio (enterprise value / EBITDA)",
    ),
    "dividend_yield": FactorSpec(
        id="dividend_yield",
        expression="fundamentals.dps_ttm / market.close",
        dependencies=("fundamentals.dps_ttm", "market.close"),
        description="Trailing twelve-month dividend yield",
    ),
    "bp_ratio": FactorSpec(
        id="bp_ratio",
        expression=(
            "fundamentals.total_equity / (market.close * fundamentals.total_shares)"
        ),
        dependencies=(
            "fundamentals.total_equity",
            "market.close",
            "fundamentals.total_shares",
        ),
        description="Book-to-Price ratio (Barra BP)",
    ),
    "ep_ttm": FactorSpec(
        id="ep_ttm",
        expression=(
            "fundamentals.net_income_ttm / (market.close * fundamentals.total_shares)"
        ),
        dependencies=(
            "fundamentals.net_income_ttm",
            "market.close",
            "fundamentals.total_shares",
        ),
        description="Trailing twelve-month earnings yield",
    ),
    "ev_to_sales": FactorSpec(
        id="ev_to_sales",
        expression=(
            "(market.close * fundamentals.total_shares "
            "+ fundamentals.total_debt - fundamentals.cash) "
            "/ fundamentals.revenue_ttm"
        ),
        dependencies=(
            "market.close",
            "fundamentals.total_shares",
            "fundamentals.total_debt",
            "fundamentals.cash",
            "fundamentals.revenue_ttm",
        ),
        description="Inverse EV/Sales ratio (enterprise value / TTM revenue)",
    ),
    "pcf_ttm": FactorSpec(
        id="pcf_ttm",
        expression=(
            "fundamentals.ocf_ttm / (market.close * fundamentals.total_shares)"
        ),
        dependencies=(
            "fundamentals.ocf_ttm",
            "market.close",
            "fundamentals.total_shares",
        ),
        description="TTM cash flow yield (OCF / market cap)",
    ),
}
