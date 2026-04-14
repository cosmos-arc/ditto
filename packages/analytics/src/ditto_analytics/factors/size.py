"""Size factor definitions — market capitalization and float factors."""

from __future__ import annotations

from ditto_analytics.factors.spec import FactorSpec

__all__ = ["SIZES"]

SIZES: dict[str, FactorSpec] = {
    "log_market_cap": FactorSpec(
        id="log_market_cap",
        expression="log(market.close * fundamentals.total_shares)",
        dependencies=("market.close", "fundamentals.total_shares"),
        description="Logarithm of total market capitalization",
    ),
    "log_free_float_cap": FactorSpec(
        id="log_free_float_cap",
        expression="log(market.close * fundamentals.free_float_shares)",
        dependencies=("market.close", "fundamentals.free_float_shares"),
        description="Logarithm of free-float market capitalization",
    ),
    "size_nl": FactorSpec(
        id="size_nl",
        expression="power(log_market_cap, 3)",
        dependencies=("log_market_cap",),
        description="Non-linear size factor (Barra SIZENL): cube of log market cap",
    ),
    "market_cap_rank": FactorSpec(
        id="market_cap_rank",
        expression="cs_rank(log_market_cap)",
        dependencies=("log_market_cap",),
        description="Cross-sectional rank of log market capitalization",
    ),
    "free_float_ratio": FactorSpec(
        id="free_float_ratio",
        expression="fundamentals.free_float_shares / fundamentals.total_shares",
        dependencies=("fundamentals.free_float_shares", "fundamentals.total_shares"),
        description="Free-float share ratio",
    ),
}
