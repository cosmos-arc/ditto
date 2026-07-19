"""Momentum and reversal factor definitions."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

__all__ = ["MOMENTUMS"]

MOMENTUMS: dict[str, FactorSpec] = {
    "relative_strength_60d": FactorSpec(
        id="relative_strength_60d",
        expression="",
        dependencies=("market.close",),
        description=("60-day return relative to a pre-registered certified benchmark"),
        computation_type="python",
    ),
    "reversal_1m": FactorSpec(
        id="reversal_1m",
        expression="-ts_pct_change(market.close, 20)",
        dependencies=("market.close",),
        description="1-month price reversal (negative 20-day return)",
    ),
    "reversal_3d": FactorSpec(
        id="reversal_3d",
        expression="-ts_pct_change(market.close, 3)",
        dependencies=("market.close",),
        description="3-day short-term reversal",
    ),
    "momentum_3m": FactorSpec(
        id="momentum_3m",
        expression="ts_pct_change(market.close, 60)",
        dependencies=("market.close",),
        description="3-month price momentum (60-day return)",
    ),
    "umd_6m": FactorSpec(
        id="umd_6m",
        expression="ts_pct_change(market.close, 126) - ts_pct_change(market.close, 21)",
        dependencies=("market.close",),
        description="Classic UMD momentum: 6-month return excluding recent 1-month",
    ),
    "momentum_accel": FactorSpec(
        id="momentum_accel",
        expression="ts_delta(returns_20, 20)",
        dependencies=("returns_20",),
        description="Momentum acceleration: 20-day change in 20-day returns",
    ),
    "sequential_momentum": FactorSpec(
        id="sequential_momentum",
        expression="sign(returns_20) * sign(returns_60)",
        dependencies=("returns_20", "returns_60"),
        description="Sequential momentum: short vs medium-term trend agreement",
    ),
    "idio_momentum": FactorSpec(
        id="idio_momentum",
        expression="",
        dependencies=("returns_1",),
        description="Idiosyncratic momentum: FF3 regression residual momentum",
        computation_type="python",
    ),
}
