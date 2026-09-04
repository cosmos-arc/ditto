"""Closed v1 technical-indicator registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["TechnicalIndicatorDefinition", "indicator_registry"]


@dataclass(frozen=True, slots=True)
class TechnicalIndicatorDefinition:
    """Stable metadata for one supported indicator output."""

    name: str
    version: str
    category: Literal["return", "trend", "momentum", "risk", "activity", "range"]


_REGISTRY = (
    TechnicalIndicatorDefinition("return", "1", "return"),
    TechnicalIndicatorDefinition("relative_return_benchmark", "1", "return"),
    TechnicalIndicatorDefinition("relative_return_industry", "1", "return"),
    TechnicalIndicatorDefinition("sma", "1", "trend"),
    TechnicalIndicatorDefinition("ema", "1", "trend"),
    TechnicalIndicatorDefinition("slope", "1", "trend"),
    TechnicalIndicatorDefinition("rsi", "1", "momentum"),
    TechnicalIndicatorDefinition("macd", "1", "momentum"),
    TechnicalIndicatorDefinition("macd_signal", "1", "momentum"),
    TechnicalIndicatorDefinition("macd_histogram", "1", "momentum"),
    TechnicalIndicatorDefinition("atr", "1", "risk"),
    TechnicalIndicatorDefinition("historical_volatility", "1", "risk"),
    TechnicalIndicatorDefinition("volume", "1", "activity"),
    TechnicalIndicatorDefinition("relative_volume", "1", "activity"),
    TechnicalIndicatorDefinition("turnover", "1", "activity"),
    TechnicalIndicatorDefinition("donchian_high", "1", "range"),
    TechnicalIndicatorDefinition("donchian_low", "1", "range"),
    TechnicalIndicatorDefinition("breakout", "1", "range"),
)


def indicator_registry() -> tuple[TechnicalIndicatorDefinition, ...]:
    """Return the immutable ordered v1 registry."""
    return _REGISTRY
