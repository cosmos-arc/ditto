"""
图表叠加用的指标全序列计算。

复用 registry 既有指标公式（逐点调用 `service` 内同一权威函数），
不引入任何新指标；warm-up 段（该指标在 registry 口径下尚不可得）输出 None，
由消费方渲染为断口。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl

from ditto_features.technical_analysis import service as _registry
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisSpec,
    TechnicalTimeframe,
)

Series = list[float | None]

SUPPORTED_OVERLAYS = frozenset({"ma", "donchian", "macd", "rsi", "atr"})

# 参数口径全部取自 registry spec 默认值，避免双处漂移。
_SPEC = TechnicalAnalysisSpec(
    spec_id="overlay-defaults",
    spec_version="1",
    algorithm_version="technical-analysis.v1",
    timeframes=(TechnicalTimeframe.DAILY,),
)


def _sma_prefix(closes: Sequence[float], window: int) -> float:
    return sum(closes[-window:]) / window


def sma_series(closes: Sequence[float], window: int) -> Series:
    """滚动简单均线（与 registry `sma` 同式），前 window-1 点 warm-up。"""
    return [
        _sma_prefix(closes[: index + 1], window) if index >= window - 1 else None
        for index in range(len(closes))
    ]


def macd_series(
    closes: Sequence[float], *, fast: int, slow: int, signal: int
) -> tuple[Series, Series, Series]:
    """
    MACD 全序列（与 registry `_momentum_readings` 同式：EMA 差 + 信号 EMA）。

    registry 就绪条件 len >= slow + signal - 1，序列首valid索引同口径。
    """
    first_valid = slow + signal - 2
    fast_ema = _registry.ema_values(closes, fast)
    slow_ema = _registry.ema_values(closes, slow)
    macd = [left - right for left, right in zip(fast_ema, slow_ema, strict=True)]
    signal_line = _registry.ema_values(macd, signal)
    histogram = [m - s for m, s in zip(macd, signal_line, strict=True)]

    def _mask(values: list[float]) -> Series:
        return [values[i] if i >= first_valid else None for i in range(len(values))]

    return _mask(macd), _mask(signal_line), _mask(histogram)


def rsi_series(closes: Sequence[float], window: int) -> Series:
    """RSI 全序列（与 registry `_rsi` 同式：简单平均涨跌幅，需 window+1 点）。"""
    return [
        _registry.rsi_value(closes[: index + 1], window) if index >= window else None
        for index in range(len(closes))
    ]


def atr_series(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    window: int,
) -> Series:
    """ATR 全序列（与 registry `_atr` 同式：真实波幅简单均值，需 window 根 TR）。"""
    return [
        _registry.atr_value(
            closes[: index + 1], highs[: index + 1], lows[: index + 1], window
        )
        if index >= window
        else None
        for index in range(len(closes))
    ]


def donchian_series(
    highs: Sequence[float], lows: Sequence[float], window: int
) -> tuple[Series, Series]:
    """Donchian 上下轨: 同 registry 口径, 取不含当前 bar 的前 window 根高低。"""
    upper: Series = []
    lower: Series = []
    for index in range(len(highs)):
        if index < window:
            upper.append(None)
            lower.append(None)
            continue
        window_highs = highs[index - window : index]
        window_lows = lows[index - window : index]
        upper.append(max(window_highs))
        lower.append(min(window_lows))
    return upper, lower


def compute_overlay_series(
    frame: pl.DataFrame,
    *,
    ma_windows: Sequence[int] = (),
    include: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Series]:
    """按需计算叠加序列，键：ma_{w}/macd/macd_signal/macd_histogram/rsi/atr/donchian_high/donchian_low。"""
    unknown = set(include) - SUPPORTED_OVERLAYS
    if unknown:
        message = f"unsupported overlays: {sorted(unknown)}"
        raise ValueError(message)
    closes = frame.get_column("close").to_list()
    highs = frame.get_column("high").to_list()
    lows = frame.get_column("low").to_list()
    output: dict[str, Series] = {}
    if "ma" in include:
        for window in ma_windows:
            output[f"ma_{window}"] = sma_series(closes, window)
    if "macd" in include:
        macd, signal, histogram = macd_series(
            closes,
            fast=_SPEC.macd_fast,
            slow=_SPEC.macd_slow,
            signal=_SPEC.macd_signal,
        )
        output["macd"] = macd
        output["macd_signal"] = signal
        output["macd_histogram"] = histogram
    if "rsi" in include:
        output["rsi"] = rsi_series(closes, _SPEC.rsi_window)
    if "atr" in include:
        output["atr"] = atr_series(closes, highs, lows, _SPEC.atr_window)
    if "donchian" in include:
        upper, lower = donchian_series(highs, lows, _SPEC.donchian_window)
        output["donchian_high"] = upper
        output["donchian_low"] = lower
    return output


def series_alignment(frame: pl.DataFrame) -> list[str]:
    """叠加序列与 bar 的对齐键（交易日升序）。"""
    return frame.get_column("trade_date").cast(pl.String).to_list()


def overlay_parameter_summary() -> Mapping[str, str]:
    """叠加参数口径说明（供 API 响应的 parameters 字段）。"""
    return {
        "sma_windows": "请求指定",
        "macd": "fast=12, slow=26, signal=9(registry 默认)",
        "rsi": "window=14(registry 默认)",
        "atr": "window=14(registry 默认)",
        "donchian": "window=20(registry 默认)",
    }
