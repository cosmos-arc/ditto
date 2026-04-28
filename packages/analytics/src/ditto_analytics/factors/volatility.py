"""Volatility factor definitions — risk and dispersion measures."""

from __future__ import annotations

from ditto_analytics.factors.spec import FactorSpec

__all__ = ["VOLATILITIES"]

VOLATILITIES: dict[str, FactorSpec] = {
    "idiosyncratic_vol": FactorSpec(
        id="idiosyncratic_vol",
        expression="",
        dependencies=("returns_1",),
        description="Idiosyncratic vol: FF3 regression residual std",
        computation_type="python",
    ),
    "downside_beta": FactorSpec(
        id="downside_beta",
        expression="",
        dependencies=("returns_1",),
        description="Downside beta: down-market covariance / variance",
        computation_type="python",
    ),
    "beta_252": FactorSpec(
        id="beta_252",
        expression="",
        dependencies=("returns_1",),
        description="Market beta: 252-day correlation with market index returns",
        computation_type="python",
    ),
    "cmra": FactorSpec(
        id="cmra",
        expression="ts_max(returns_20, 240) - ts_min(returns_20, 240)",
        dependencies=("returns_20",),
        description="CMRA (Barra): max-min of 20-day returns over ~12 months",
    ),
    "realized_skewness": FactorSpec(
        id="realized_skewness",
        expression="",
        dependencies=("returns_1",),
        description="Realized return skewness over rolling window",
        computation_type="python",
    ),
    "vol_ratio": FactorSpec(
        id="vol_ratio",
        expression="volatility_20 / volatility_60",
        dependencies=("volatility_20", "volatility_60"),
        description="Volatility ratio: short-term vs long-term return volatility",
    ),
    "volatility_60": FactorSpec(
        id="volatility_60",
        expression="ts_std(returns_1, 60) * sqrt(252)",
        dependencies=("returns_1",),
        description="Annualized 60-day return volatility",
    ),
    "volatility_120": FactorSpec(
        id="volatility_120",
        expression="ts_std(returns_1, 120) * sqrt(252)",
        dependencies=("returns_1",),
        description="Annualized 120-day return volatility",
    ),
    "parkinson_vol": FactorSpec(
        id="parkinson_vol",
        expression="",
        dependencies=("market.high", "market.low"),
        description="Parkinson volatility: high-low range estimator",
        computation_type="python",
    ),
    "garman_klass_vol": FactorSpec(
        id="garman_klass_vol",
        expression="",
        dependencies=("market.open", "market.high", "market.low", "market.close"),
        description="Garman-Klass volatility: OHLC-based estimator",
        computation_type="python",
    ),
    "overnight_vol": FactorSpec(
        id="overnight_vol",
        expression="ts_std(market.open / market.close - 1, 20) * sqrt(252)",
        dependencies=("market.open", "market.close"),
        description="Annualized overnight (close-to-open) return volatility",
    ),
    "intraday_vol": FactorSpec(
        id="intraday_vol",
        expression="ts_std(market.high / market.low - 1, 20) * sqrt(252)",
        dependencies=("market.high", "market.low"),
        description="Annualized intraday (high/low range) return volatility",
    ),
}
