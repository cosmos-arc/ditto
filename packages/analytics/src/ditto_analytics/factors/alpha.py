"""Alpha factor definitions — composite factors for quantitative strategies."""

from __future__ import annotations

from ditto_analytics.factors.spec import FactorSpec

__all__ = ["ALPHAS"]

ALPHAS: dict[str, FactorSpec] = {
    "momentum_1m": FactorSpec(
        id="momentum_1m",
        expression="ts_pct_change(market.close, 20)",
        dependencies=("market.close",),
        description="1-month price momentum (20-day return)",
    ),
    "momentum_12m": FactorSpec(
        id="momentum_12m",
        expression="ts_pct_change(market.close, 252)",
        dependencies=("market.close",),
        description="12-month price momentum (252-day return)",
    ),
    "reversal_1w": FactorSpec(
        id="reversal_1w",
        expression="-ts_pct_change(market.close, 5)",
        dependencies=("market.close",),
        description="1-week price reversal (negative 5-day return)",
    ),
    "value_pe": FactorSpec(
        id="value_pe",
        expression="-pe_ratio",
        dependencies=("pe_ratio",),
        description="Value factor based on inverse PE ratio",
    ),
    "value_pb": FactorSpec(
        id="value_pb",
        expression="-pb_ratio",
        dependencies=("pb_ratio",),
        description="Value factor based on inverse PB ratio",
    ),
    "quality_roe": FactorSpec(
        id="quality_roe",
        expression="roe",
        dependencies=("roe",),
        description="Quality factor based on ROE",
    ),
    "quality_margin": FactorSpec(
        id="quality_margin",
        expression="net_margin",
        dependencies=("net_margin",),
        description="Quality factor based on net profit margin",
    ),
    "volatility_factor": FactorSpec(
        id="volatility_factor",
        expression="-volatility_20",
        dependencies=("volatility_20",),
        description="Low-volatility factor (negative 20-day return std)",
    ),
    "liquidity": FactorSpec(
        id="liquidity",
        expression="cs_rank(ts_mean(market.volume, 20) * market.close)",
        dependencies=("market.volume", "market.close"),
        description=(
            "Liquidity factor: cross-sectional rank of 20-day average dollar volume"
        ),
    ),
    "alpha_001": FactorSpec(
        id="alpha_001",
        expression="cs_rank(ts_corr(returns_1, ts_delay(returns_1, 5), 20))",
        dependencies=("returns_1",),
        description=(
            "Alpha 001: cross-sectional rank of autocorrelation (lag-5, 20-day window)"
        ),
    ),
}
