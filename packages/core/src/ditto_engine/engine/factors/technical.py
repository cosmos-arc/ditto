"""Technical indicator factor definitions."""

from __future__ import annotations

from ditto_engine.engine.factors.spec import FactorSpec

__all__ = ["TECHNICALS"]

_WINDOWS = (5, 10, 14, 20, 60)

_return_windows = (5, 10, 20, 60)

_ma_specs: dict[str, FactorSpec] = {
    f"ma_{n}": FactorSpec(
        id=f"ma_{n}",
        expression=f"ts_mean(market.close, {n})",
        dependencies=("market.close",),
        description=f"Simple moving average of close price (window={n})",
    )
    for n in _WINDOWS
}

_ema_specs: dict[str, FactorSpec] = {
    f"ema_{n}": FactorSpec(
        id=f"ema_{n}",
        expression=f"ts_ema(market.close, {n})",
        dependencies=("market.close",),
        description=f"Exponential moving average of close price (window={n})",
    )
    for n in _WINDOWS
}

_rsi_specs: dict[str, FactorSpec] = {
    f"rsi_{n}": FactorSpec(
        id=f"rsi_{n}",
        expression=(
            f"100 - 100 / (1 + ts_mean(returns_1, {n}) / ts_mean(abs(returns_1), {n}))"
        ),
        dependencies=("returns_1",),
        description=f"Relative Strength Index (window={n})",
    )
    for n in (14, 6)
}

_macd_specs: dict[str, FactorSpec] = {
    "macd": FactorSpec(
        id="macd",
        expression="ts_ema(market.close, 12) - ts_ema(market.close, 26)",
        dependencies=("market.close",),
        description="MACD line: EMA(12) - EMA(26)",
    ),
    "macd_signal": FactorSpec(
        id="macd_signal",
        expression="ts_ema(macd, 9)",
        dependencies=("macd",),
        description="MACD signal line: EMA(9) of MACD",
    ),
    "macd_hist": FactorSpec(
        id="macd_hist",
        expression="macd - macd_signal",
        dependencies=("macd", "macd_signal"),
        description="MACD histogram: MACD - Signal",
    ),
}

_bollinger_specs: dict[str, FactorSpec] = {
    "bollinger_middle": FactorSpec(
        id="bollinger_middle",
        expression="ts_mean(market.close, 20)",
        dependencies=("market.close",),
        description="Bollinger middle band: SMA(20)",
    ),
    "bollinger_upper": FactorSpec(
        id="bollinger_upper",
        expression="ts_mean(market.close, 20) + 2 * ts_std(market.close, 20)",
        dependencies=("market.close",),
        description="Bollinger upper band: SMA(20) + 2*STD(20)",
    ),
    "bollinger_lower": FactorSpec(
        id="bollinger_lower",
        expression="ts_mean(market.close, 20) - 2 * ts_std(market.close, 20)",
        dependencies=("market.close",),
        description="Bollinger lower band: SMA(20) - 2*STD(20)",
    ),
}

_atr_specs: dict[str, FactorSpec] = {
    f"atr_{n}": FactorSpec(
        id=f"atr_{n}",
        expression=f"ts_mean(tr, {n})",
        dependencies=("tr",),
        description=f"Average True Range (window={n})",
    )
    for n in (14, 20)
}

_volatility_specs: dict[str, FactorSpec] = {
    f"volatility_{n}": FactorSpec(
        id=f"volatility_{n}",
        expression=f"ts_std(returns_1, {n})",
        dependencies=("returns_1",),
        description=f"Return volatility: rolling std of daily returns (window={n})",
    )
    for n in _WINDOWS
}

_volume_ma_specs: dict[str, FactorSpec] = {
    f"volume_ma_{n}": FactorSpec(
        id=f"volume_ma_{n}",
        expression=f"ts_mean(market.volume, {n})",
        dependencies=("market.volume",),
        description=f"Volume moving average (window={n})",
    )
    for n in _WINDOWS
}

_returns_specs: dict[str, FactorSpec] = {
    f"returns_{n}": FactorSpec(
        id=f"returns_{n}",
        expression=f"ts_pct_change(market.close, {n})",
        dependencies=("market.close",),
        description=f"{n}-day price return",
    )
    for n in _return_windows
}

TECHNICALS: dict[str, FactorSpec] = {
    **_ma_specs,
    **_ema_specs,
    **_rsi_specs,
    **_macd_specs,
    **_bollinger_specs,
    **_atr_specs,
    **_volatility_specs,
    **_volume_ma_specs,
    **_returns_specs,
}
