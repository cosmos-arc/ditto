"""
Metadata models for technical indicators.

技术指标元数据模型，定义指标类型和元数据结构.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Valid indicator types (based on ScienceDirect 2025 research)
IndicatorType = Literal["trend", "momentum", "volatility", "volume"]


@dataclass(frozen=True)
class IndicatorMetadata:
    """
    Technical indicator metadata.

    技术指标元数据，包含指标的标识、名称、类型、描述和参数.

    Attributes:
        indicator_id: Unique identifier (e.g., "indicator_rsi_14")
        name: Display name (e.g., "RSI(14)")
        type: Indicator category
        description: Human-readable description
        formula: Calculation formula
        parameters: Calculation parameters (e.g., {"period": 14})

    """

    indicator_id: str
    name: str
    type: IndicatorType
    description: str
    formula: str
    parameters: dict[str, object]
    status: str = "active"


# Predefined indicator types
INDICATOR_TYPE_TREND = "trend"
INDICATOR_TYPE_MOMENTUM = "momentum"
INDICATOR_TYPE_VOLATILITY = "volatility"
INDICATOR_TYPE_VOLUME = "volume"


__all__ = [
    "INDICATOR_TYPE_MOMENTUM",
    "INDICATOR_TYPE_TREND",
    "INDICATOR_TYPE_VOLATILITY",
    "INDICATOR_TYPE_VOLUME",
    "IndicatorMetadata",
    "IndicatorType",
]
