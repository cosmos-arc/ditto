"""Alternative factor definitions — margin trading and pledge."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

__all__ = ["ALTERNATIVES"]

ALTERNATIVES: dict[str, FactorSpec] = {
    "margin_change": FactorSpec(
        id="margin_change",
        expression="ts_pct_change(capital.margin_buy, 20)",
        dependencies=("capital.margin_buy",),
        description="20-day change in margin buying amount",
    ),
    "pledge_ratio": FactorSpec(
        id="pledge_ratio",
        expression="capital.pledge_shares / capital.total_shares",
        dependencies=("capital.pledge_shares", "capital.total_shares"),
        description="Equity pledge ratio: pledged shares / total shares",
    ),
    "short_interest_ratio": FactorSpec(
        id="short_interest_ratio",
        expression=(
            "capital.short_balance / (market.close * fundamentals.total_shares)"
        ),
        dependencies=(
            "capital.short_balance",
            "market.close",
            "fundamentals.total_shares",
        ),
        description="Short interest ratio: short balance / market capitalization",
    ),
}
