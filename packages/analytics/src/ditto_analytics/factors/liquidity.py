"""Liquidity factor definitions — turnover, illiquidity, and volume-price factors."""

from __future__ import annotations

from ditto_analytics.factors.spec import FactorSpec

__all__ = ["LIQUIDITIES"]

# Private intermediate factors for complex computations
_raw_mf: dict[str, FactorSpec] = {
    "raw_mf": FactorSpec(
        id="raw_mf",
        expression="tp * market.volume",
        dependencies=("tp", "market.volume"),
        description="Raw money flow: typical price * volume",
    ),
}

_turnover_specs: dict[str, FactorSpec] = {
    "turnover_20d": FactorSpec(
        id="turnover_20d",
        expression="ts_mean(market.volume / fundamentals.free_float_shares, 20)",
        dependencies=("market.volume", "fundamentals.free_float_shares"),
        description="20-day average turnover rate",
    ),
    "turnover_change": FactorSpec(
        id="turnover_change",
        expression="turnover_20d / ts_delay(turnover_20d, 20) - 1",
        dependencies=("turnover_20d",),
        description="Turnover rate change: current 20d avg vs 20d-ago 20d avg",
    ),
    "turnover_stability": FactorSpec(
        id="turnover_stability",
        expression="-ts_std(turnover_20d, 60)",
        dependencies=("turnover_20d",),
        description="Turnover stability: neg. rolling std of 20d turnover",
    ),
}

_illiquidity_specs: dict[str, FactorSpec] = {
    "amihud_illiquidity": FactorSpec(
        id="amihud_illiquidity",
        expression="ts_mean(abs(returns_1) / (market.volume * market.close), 20)",
        dependencies=("returns_1", "market.volume", "market.close"),
        description="Amihud illiquidity ratio: average of |return| / dollar volume",
    ),
}

_volume_price_specs: dict[str, FactorSpec] = {
    "volume_price_corr": FactorSpec(
        id="volume_price_corr",
        expression="ts_corr(market.volume, returns_1, 20)",
        dependencies=("market.volume", "returns_1"),
        description="Volume-price correlation over 20 days",
    ),
    "mfi_14": FactorSpec(
        id="mfi_14",
        expression=(
            "100 - 100 / (1 + "
            "ts_sum(if_else(raw_mf > ts_delay(raw_mf, 1), raw_mf, 0), 14) "
            "/ ts_sum(if_else(raw_mf < ts_delay(raw_mf, 1), abs(raw_mf), 0), 14))"
        ),
        dependencies=("raw_mf",),
        description="Money Flow Index (14-day): volume-weighted RSI",
    ),
    "obv": FactorSpec(
        id="obv",
        expression="",
        dependencies=("market.close", "market.volume"),
        description="On-Balance Volume: cumulative volume flow by price direction",
        computation_type="python",
    ),
}

LIQUIDITIES: dict[str, FactorSpec] = {
    **_raw_mf,
    **_turnover_specs,
    **_illiquidity_specs,
    **_volume_price_specs,
}
