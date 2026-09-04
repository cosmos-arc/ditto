"""Polars-backed deterministic technical indicator service."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from typing import cast

import polars as pl

from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisSnapshot,
    TechnicalAnalysisSpec,
    TechnicalBar,
    TechnicalConflict,
    TechnicalDirection,
    TechnicalIndicatorParameter,
    TechnicalIndicatorReading,
    TechnicalIndicatorStatus,
    TechnicalLevel,
    TechnicalLevelKind,
    TechnicalTimeframe,
    TechnicalTimeframeSummary,
    canonical_input_hash,
    canonical_snapshot_hash,
    canonical_spec_hash,
)
from ditto_features.technical_analysis.registry import indicator_registry

__all__ = ["TechnicalAnalysisService"]

_REGISTRY_VERSION = "technical-indicator-registry.v1"
_ANNUALIZATION = math.sqrt(252.0)
_RSI_BULLISH = 55.0
_RSI_BEARISH = 45.0


def _ema(values: Sequence[float], window: int) -> list[float]:
    alpha = 2.0 / (window + 1.0)
    output: list[float] = []
    for value in values:
        output.append(
            value if not output else alpha * value + (1.0 - alpha) * output[-1]
        )
    return output


def _ready(
    *,
    name: str,
    timeframe: TechnicalTimeframe,
    window: int | None,
    value: float,
    parameters: tuple[TechnicalIndicatorParameter, ...] = (),
) -> TechnicalIndicatorReading:
    return TechnicalIndicatorReading(
        name=name,
        timeframe=timeframe,
        indicator_version="1",
        window=window,
        parameters=parameters,
        value=float(value),
        status=TechnicalIndicatorStatus.READY,
        reason=None,
    )


def _not_ready(
    *,
    name: str,
    timeframe: TechnicalTimeframe,
    window: int | None,
    unavailable: bool = False,
    reason: str | None = None,
    parameters: tuple[TechnicalIndicatorParameter, ...] = (),
) -> TechnicalIndicatorReading:
    return TechnicalIndicatorReading(
        name=name,
        timeframe=timeframe,
        indicator_version="1",
        window=window,
        parameters=parameters,
        value=None,
        status=(
            TechnicalIndicatorStatus.UNAVAILABLE
            if unavailable
            else TechnicalIndicatorStatus.WARMING_UP
        ),
        reason=(
            reason
            or ("missing_reference_series" if unavailable else "insufficient_history")
        ),
    )


def _parameter(name: str, value: int) -> TechnicalIndicatorParameter:
    return TechnicalIndicatorParameter(name=name, value=value)


def _visible_bars(value: TechnicalAnalysisInput) -> tuple[TechnicalBar, ...]:
    return tuple(
        item
        for item in value.bars
        if item.occurred_at < value.as_of
        and item.knowledge_at <= value.knowledge_cutoff
        and item.publication_at <= value.publication_cutoff
    )


def _frame(bars: tuple[TechnicalBar, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "occurred_at": [item.occurred_at for item in bars],
            "open": [item.open * item.adjustment_factor for item in bars],
            "high": [item.high * item.adjustment_factor for item in bars],
            "low": [item.low * item.adjustment_factor for item in bars],
            "close": [item.close * item.adjustment_factor for item in bars],
            "volume": [item.volume for item in bars],
            "turnover": [item.turnover for item in bars],
            "benchmark_close": [item.benchmark_close for item in bars],
            "industry_close": [item.industry_close for item in bars],
            "suspended": [item.suspended for item in bars],
        }
    ).sort("occurred_at")


def _weekly(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    return (
        frame.with_columns(pl.col("occurred_at").dt.strftime("%G-%V").alias("_week"))
        .group_by("_week", maintain_order=True)
        .agg(
            pl.col("occurred_at").max(),
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("turnover").sum(),
            pl.col("benchmark_close").drop_nulls().last(),
            pl.col("industry_close").drop_nulls().last(),
            pl.col("suspended").all(),
        )
        .drop("_week")
    )


def _float_values(frame: pl.DataFrame, column: str) -> list[float]:
    return [float(item) for item in frame.get_column(column).to_list()]


def _optional_float_values(frame: pl.DataFrame, column: str) -> list[float] | None:
    values = frame.get_column(column).to_list()
    if any(item is None for item in values):
        return None
    return [float(item) for item in values]


def _window_reading(
    *,
    name: str,
    timeframe: TechnicalTimeframe,
    window: int,
    values: Sequence[float],
    function: Callable[[Sequence[float]], float],
    required: int | None = None,
) -> TechnicalIndicatorReading:
    minimum = required if required is not None else window
    parameters = (_parameter("window", window),)
    if len(values) < minimum:
        return _not_ready(
            name=name,
            timeframe=timeframe,
            window=window,
            parameters=parameters,
        )
    result = function(values)
    return _ready(
        name=name,
        timeframe=timeframe,
        window=window,
        value=float(result),
        parameters=parameters,
    )


type _ReadingMap = dict[str, TechnicalIndicatorReading]


def _period_return(series: Sequence[float], window: int) -> float:
    return series[-1] / series[-(window + 1)] - 1.0


def _return_readings(
    closes: Sequence[float],
    benchmark: Sequence[float] | None,
    industry: Sequence[float] | None,
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    window = spec.return_window
    result = {
        "return": _window_reading(
            name="return",
            timeframe=timeframe,
            window=window,
            values=closes,
            required=window + 1,
            function=lambda series: _period_return(series, window),
        )
    }
    parameters = (_parameter("window", window),)
    for name, reference in (
        ("relative_return_benchmark", benchmark),
        ("relative_return_industry", industry),
    ):
        if reference is None:
            result[name] = _not_ready(
                name=name,
                timeframe=timeframe,
                window=window,
                unavailable=True,
                parameters=parameters,
            )
        elif len(closes) < window + 1:
            result[name] = _not_ready(
                name=name,
                timeframe=timeframe,
                window=window,
                parameters=parameters,
            )
        else:
            result[name] = _ready(
                name=name,
                timeframe=timeframe,
                window=window,
                value=_period_return(closes, window)
                - _period_return(reference, window),
                parameters=parameters,
            )
    return result


def _trend_readings(
    closes: Sequence[float],
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    return {
        "sma": _window_reading(
            name="sma",
            timeframe=timeframe,
            window=spec.trend_window,
            values=closes,
            function=lambda series: (
                sum(series[-spec.trend_window :]) / spec.trend_window
            ),
        ),
        "ema": _window_reading(
            name="ema",
            timeframe=timeframe,
            window=spec.trend_window,
            values=closes,
            function=lambda series: _ema(series, spec.trend_window)[-1],
        ),
        "slope": _window_reading(
            name="slope",
            timeframe=timeframe,
            window=spec.slope_window,
            values=closes,
            function=lambda series: (
                (series[-1] - series[-spec.slope_window]) / (spec.slope_window - 1)
            ),
        ),
    }


def _rsi(series: Sequence[float], window: int) -> float:
    changes = [
        series[index] - series[index - 1]
        for index in range(len(series) - window, len(series))
    ]
    gain = sum(max(item, 0.0) for item in changes) / window
    loss = sum(max(-item, 0.0) for item in changes) / window
    return 100.0 if loss == 0.0 else 100.0 - 100.0 / (1.0 + gain / loss)


def _momentum_readings(
    closes: Sequence[float],
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    result = {
        "rsi": _window_reading(
            name="rsi",
            timeframe=timeframe,
            window=spec.rsi_window,
            values=closes,
            required=spec.rsi_window + 1,
            function=lambda series: _rsi(series, spec.rsi_window),
        )
    }
    parameters = (
        _parameter("fast", spec.macd_fast),
        _parameter("slow", spec.macd_slow),
        _parameter("signal", spec.macd_signal),
    )
    names = ("macd", "macd_signal", "macd_histogram")
    if len(closes) < spec.macd_slow + spec.macd_signal - 1:
        result.update(
            {
                name: _not_ready(
                    name=name,
                    timeframe=timeframe,
                    window=spec.macd_slow,
                    parameters=parameters,
                )
                for name in names
            }
        )
        return result
    fast = _ema(closes, spec.macd_fast)
    slow = _ema(closes, spec.macd_slow)
    macd = [left - right for left, right in zip(fast, slow, strict=True)]
    signal = _ema(macd, spec.macd_signal)
    outputs = (macd[-1], signal[-1], macd[-1] - signal[-1])
    result.update(
        {
            name: _ready(
                name=name,
                timeframe=timeframe,
                window=spec.macd_slow,
                value=output,
                parameters=parameters,
            )
            for name, output in zip(names, outputs, strict=True)
        }
    )
    return result


def _atr(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    window: int,
) -> float:
    ranges = [
        max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )
        for index in range(len(closes) - window, len(closes))
    ]
    return sum(ranges) / window


def _volatility(series: Sequence[float], window: int) -> float:
    returns = [
        series[index] / series[index - 1] - 1.0
        for index in range(len(series) - window, len(series))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    return math.sqrt(variance) * _ANNUALIZATION


def _risk_readings(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    return {
        "atr": _window_reading(
            name="atr",
            timeframe=timeframe,
            window=spec.atr_window,
            values=closes,
            required=spec.atr_window + 1,
            function=lambda _: _atr(closes, highs, lows, spec.atr_window),
        ),
        "historical_volatility": _window_reading(
            name="historical_volatility",
            timeframe=timeframe,
            window=spec.volatility_window,
            values=closes,
            required=spec.volatility_window + 1,
            function=lambda series: _volatility(series, spec.volatility_window),
        ),
    }


def _activity_readings(
    volumes: Sequence[float],
    turnovers: Sequence[float],
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    result: _ReadingMap = {}
    for name, values in (("volume", volumes), ("turnover", turnovers)):
        result[name] = (
            _ready(
                name=name,
                timeframe=timeframe,
                window=None,
                value=values[-1],
            )
            if values
            else _not_ready(name=name, timeframe=timeframe, window=None)
        )
    window = spec.volume_window
    if len(volumes) < window + 1:
        result["relative_volume"] = _not_ready(
            name="relative_volume",
            timeframe=timeframe,
            window=window,
            parameters=(_parameter("window", window),),
        )
        return result
    baseline = sum(volumes[-(window + 1) : -1]) / window
    result["relative_volume"] = (
        _not_ready(
            name="relative_volume",
            timeframe=timeframe,
            window=window,
            unavailable=True,
            reason="zero_volume_baseline",
            parameters=(_parameter("window", window),),
        )
        if baseline == 0.0
        else _ready(
            name="relative_volume",
            timeframe=timeframe,
            window=window,
            value=volumes[-1] / baseline,
            parameters=(_parameter("window", window),),
        )
    )
    return result


def _range_readings(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    timeframe: TechnicalTimeframe,
    spec: TechnicalAnalysisSpec,
) -> _ReadingMap:
    names = ("donchian_high", "donchian_low", "breakout")
    window = spec.donchian_window
    parameters = (_parameter("window", window),)
    if len(closes) < window + 1:
        return {
            name: _not_ready(
                name=name,
                timeframe=timeframe,
                window=window,
                parameters=parameters,
            )
            for name in names
        }
    high = max(highs[-(window + 1) : -1])
    low = min(lows[-(window + 1) : -1])
    breakout = 1.0 if closes[-1] > high else -1.0 if closes[-1] < low else 0.0
    return {
        name: _ready(
            name=name,
            timeframe=timeframe,
            window=window,
            value=output,
            parameters=parameters,
        )
        for name, output in zip(names, (high, low, breakout), strict=True)
    }


def _readings(
    frame: pl.DataFrame,
    *,
    timeframe: TechnicalTimeframe,
    value: TechnicalAnalysisInput,
) -> tuple[TechnicalIndicatorReading, ...]:
    closes = _float_values(frame, "close")
    highs = _float_values(frame, "high")
    lows = _float_values(frame, "low")
    readings: _ReadingMap = {}
    readings.update(
        _return_readings(
            closes,
            _optional_float_values(frame, "benchmark_close"),
            _optional_float_values(frame, "industry_close"),
            timeframe=timeframe,
            spec=value.spec,
        )
    )
    readings.update(_trend_readings(closes, timeframe=timeframe, spec=value.spec))
    readings.update(_momentum_readings(closes, timeframe=timeframe, spec=value.spec))
    readings.update(
        _risk_readings(
            closes,
            highs,
            lows,
            timeframe=timeframe,
            spec=value.spec,
        )
    )
    readings.update(
        _activity_readings(
            _float_values(frame, "volume"),
            _float_values(frame, "turnover"),
            timeframe=timeframe,
            spec=value.spec,
        )
    )
    readings.update(
        _range_readings(
            closes,
            highs,
            lows,
            timeframe=timeframe,
            spec=value.spec,
        )
    )
    return tuple(readings[item.name] for item in indicator_registry())


def _levels(
    frame: pl.DataFrame,
    *,
    timeframe: TechnicalTimeframe,
    window: int,
) -> tuple[TechnicalLevel, ...]:
    if len(frame) < window + 1:
        return ()
    closes = _float_values(frame, "close")
    highs = _float_values(frame, "high")[-(window + 1) : -1]
    lows = _float_values(frame, "low")[-(window + 1) : -1]
    close = closes[-1]
    support = max((item for item in lows if item <= close), default=min(lows))
    resistance = min((item for item in highs if item >= close), default=max(highs))
    tolerance = max(close * 0.005, 1e-12)

    def level(
        kind: TechnicalLevelKind,
        price: float,
        values: Sequence[float],
    ) -> TechnicalLevel:
        touches = sum(abs(item - price) <= tolerance for item in values)
        return TechnicalLevel(
            timeframe=timeframe,
            kind=kind,
            price=price,
            confidence=min(1.0, touches / 3.0),
            touches=touches,
            window=window,
            algorithm_version="support-resistance.v1",
        )

    return (
        level(TechnicalLevelKind.SUPPORT, support, lows),
        level(TechnicalLevelKind.RESISTANCE, resistance, highs),
    )


def _reading_map(
    readings: tuple[TechnicalIndicatorReading, ...],
) -> dict[str, TechnicalIndicatorReading]:
    return {item.name: item for item in readings}


def _direction(
    value: float | None, *, upper: float = 0.0, lower: float = 0.0
) -> TechnicalDirection:
    if value is None:
        return "unknown"
    if value > upper:
        return "bullish"
    if value < lower:
        return "bearish"
    return "neutral"


def _summary(
    timeframe: TechnicalTimeframe,
    readings: tuple[TechnicalIndicatorReading, ...],
) -> TechnicalTimeframeSummary:
    indexed = _reading_map(readings)
    slope = indexed["slope"].value
    trend = _direction(slope)
    rsi = indexed["rsi"].value
    momentum: TechnicalDirection = (
        "unknown"
        if rsi is None
        else "bullish"
        if rsi > _RSI_BULLISH
        else "bearish"
        if rsi < _RSI_BEARISH
        else "neutral"
    )
    breakout = _direction(indexed["breakout"].value)
    return TechnicalTimeframeSummary(
        timeframe=timeframe,
        trend=trend,
        momentum=momentum,
        breakout=breakout,
    )


def _conflicts(
    summaries: tuple[TechnicalTimeframeSummary, ...],
) -> tuple[TechnicalConflict, ...]:
    indexed = {item.timeframe: item for item in summaries}
    daily = indexed.get(TechnicalTimeframe.DAILY)
    weekly = indexed.get(TechnicalTimeframe.WEEKLY)
    if daily is None or weekly is None:
        return ()
    output: list[TechnicalConflict] = []
    for dimension in ("trend", "momentum", "breakout"):
        daily_value = getattr(daily, dimension)
        weekly_value = getattr(weekly, dimension)
        if daily_value != weekly_value:
            output.append(
                TechnicalConflict(
                    dimension=dimension,
                    daily=daily_value,
                    weekly=weekly_value,
                    reason_code=f"daily_weekly_{dimension}_conflict",
                )
            )
    return tuple(output)


class TechnicalAnalysisService:
    """Compute the closed v1 registry without I/O or latest-data fallback."""

    def analyze(self, value: TechnicalAnalysisInput) -> TechnicalAnalysisSnapshot:
        """Evaluate one exact left-closed PIT request."""
        visible = _visible_bars(value)
        visible_frame = _frame(visible)
        computed_frame = visible_frame.filter(~pl.col("suspended"))
        warnings: set[str] = set()
        if len(computed_frame) != len(visible_frame):
            warnings.add("suspended_bar_excluded")
        factors = {item.adjustment_factor for item in visible}
        if len(factors) > 1:
            warnings.add("corporate_action_adjustment_applied")

        readings: list[TechnicalIndicatorReading] = []
        levels: list[TechnicalLevel] = []
        summaries: list[TechnicalTimeframeSummary] = []
        for timeframe in value.spec.timeframes:
            timeframe_frame = (
                computed_frame
                if timeframe is TechnicalTimeframe.DAILY
                else _weekly(computed_frame)
            )
            timeframe_readings = _readings(
                timeframe_frame,
                timeframe=timeframe,
                value=value,
            )
            readings.extend(timeframe_readings)
            levels.extend(
                _levels(
                    timeframe_frame,
                    timeframe=timeframe,
                    window=value.spec.support_resistance_window,
                )
            )
            summaries.append(_summary(timeframe, timeframe_readings))

        required = {
            (TechnicalTimeframe.DAILY, "return"),
            (TechnicalTimeframe.DAILY, "sma"),
            (TechnicalTimeframe.DAILY, "rsi"),
        }
        required_readings = [
            item for item in readings if (item.timeframe, item.name) in required
        ]
        if any(
            item.status is not TechnicalIndicatorStatus.READY
            for item in required_readings
        ):
            status = "blocked"
        elif any(
            item.status is not TechnicalIndicatorStatus.READY for item in readings
        ):
            status = "degraded"
        else:
            status = "ready"
        missing_inputs = tuple(
            sorted(
                f"{item.timeframe.value}:{item.name}:{item.reason}"
                for item in readings
                if item.status is not TechnicalIndicatorStatus.READY
            )
        )
        last_visible = (
            visible_frame.get_column("occurred_at").max()
            if not visible_frame.is_empty()
            else None
        )
        last_computed = (
            computed_frame.get_column("occurred_at").max()
            if not computed_frame.is_empty()
            else None
        )
        input_hash = canonical_input_hash(value, visible_bars=visible)
        draft = TechnicalAnalysisSnapshot(
            snapshot_id="pending",
            input_hash=input_hash,
            spec_hash=canonical_spec_hash(value.spec),
            registry_version=_REGISTRY_VERSION,
            instrument_id=value.instrument_id,
            instrument_name=value.instrument_name,
            as_of=value.as_of,
            knowledge_cutoff=value.knowledge_cutoff,
            publication_cutoff=value.publication_cutoff,
            source_snapshot_ids=value.source_snapshot_ids,
            status=status,
            last_visible_bar_at=cast(datetime | None, last_visible),
            last_computed_bar_at=cast(datetime | None, last_computed),
            readings=tuple(readings),
            levels=tuple(levels),
            timeframe_summaries=tuple(summaries),
            conflicts=_conflicts(tuple(summaries)),
            missing_inputs=missing_inputs,
            warnings=tuple(sorted(warnings)),
            selection_run_id=value.selection_run_id,
            research_case_id=value.research_case_id,
            portfolio_snapshot_id=value.portfolio_snapshot_id,
        )
        digest = canonical_snapshot_hash(draft)
        return replace(draft, snapshot_id=f"technical-analysis:sha256:{digest}")
