"""Technical indicator factor definitions."""

from __future__ import annotations

from ditto_features.factors.spec import FactorSpec

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

# Additional EMA windows for specific indicators
_extra_ema_specs: dict[str, FactorSpec] = {
    "ema_13": FactorSpec(
        id="ema_13",
        expression="ts_ema(market.close, 13)",
        dependencies=("market.close",),
        description="EMA of close price (window=13, used by Elder Ray)",
    ),
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

# --- Sprint 2: Extended technical factors (+10) ---

_cci_specs: dict[str, FactorSpec] = {
    "cci_20": FactorSpec(
        id="cci_20",
        expression=(
            "(tp - ts_mean(tp, 20)) / (0.015 * ts_mean(abs(tp - ts_mean(tp, 20)), 20))"
        ),
        dependencies=("tp",),
        description="CCI (20-day): normalized deviation from TP mean",
    ),
}

_williams_r_specs: dict[str, FactorSpec] = {
    "williams_r": FactorSpec(
        id="williams_r",
        expression=(
            "(ts_max(market.high, 14) - market.close) "
            "/ (ts_max(market.high, 14) - ts_min(market.low, 14)) "
            "* (-100)"
        ),
        dependencies=("market.high", "market.low", "market.close"),
        description="Williams %R (14-day): measures overbought/oversold levels",
    ),
}

_vwap_specs: dict[str, FactorSpec] = {
    "vwap_20d": FactorSpec(
        id="vwap_20d",
        expression="ts_sum(tp * market.volume, 20) / ts_sum(market.volume, 20)",
        dependencies=("tp", "market.volume"),
        description="20-day Volume Weighted Average Price",
    ),
}

_choppiness_specs: dict[str, FactorSpec] = {
    "choppiness_index": FactorSpec(
        id="choppiness_index",
        expression=(
            "log10(ts_sum(tr, 14) "
            "/ (ts_max(market.high, 14) - ts_min(market.low, 14))) "
            "/ log10(14)"
        ),
        dependencies=("tr", "market.high", "market.low"),
        description="Choppiness Index (14-day): ranging vs trending measure",
    ),
}

_elder_ray_specs: dict[str, FactorSpec] = {
    "elder_ray_bull": FactorSpec(
        id="elder_ray_bull",
        expression="market.high - ema_13",
        dependencies=("market.high", "ema_13"),
        description="Elder Ray Bull Power: high - EMA(13) (positive = bullish)",
    ),
}

_obv_ma20_spec: FactorSpec = FactorSpec(
    id="obv_ma20",
    expression="",
    dependencies=("obv",),
    description="20-day moving average of On-Balance Volume",
    computation_type="python",
)

_kdj_specs: dict[str, FactorSpec] = {
    "kdj_k": FactorSpec(
        id="kdj_k",
        expression="",
        dependencies=("market.high", "market.low", "market.close"),
        description="Stochastic K value (9,3,3): fast stochastic oscillator",
        computation_type="python",
    ),
    "kdj_d": FactorSpec(
        id="kdj_d",
        expression="",
        dependencies=("kdj_k",),
        description="Stochastic D value (9,3,3): smoothed K value",
        computation_type="python",
    ),
}

_supertrend_specs: dict[str, FactorSpec] = {
    "supertrend": FactorSpec(
        id="supertrend",
        expression="",
        dependencies=("market.high", "market.low", "market.close"),
        description="SuperTrend indicator: ATR-based trend-following indicator",
        computation_type="python",
    ),
}

TECHNICALS: dict[str, FactorSpec] = {
    **_ma_specs,
    **_ema_specs,
    **_extra_ema_specs,
    **_rsi_specs,
    **_macd_specs,
    **_bollinger_specs,
    **_atr_specs,
    **_volatility_specs,
    **_volume_ma_specs,
    **_returns_specs,
    **_cci_specs,
    **_williams_r_specs,
    **_vwap_specs,
    **_choppiness_specs,
    **_elder_ray_specs,
    "obv_ma20": _obv_ma20_spec,
    **_kdj_specs,
    **_supertrend_specs,
}
