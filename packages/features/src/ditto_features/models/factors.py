"""Metadata models for factors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Factor class (data source category)
FactorClass = Literal["fundamental", "technical", "macro", "statistical"]

# Factor family (investment style)
FactorFamily = Literal["value", "momentum", "quality", "size", "volatility"]


@dataclass(frozen=True)
class FactorMetadata:
    """
    Factor metadata.

    Attributes:
        factor_id: Unique identifier (e.g., "factor_momentum_12m")
        name: Display name (e.g., "12-Month Momentum")
        factor_class: Data source class
        family: Investment style family
        description: Human-readable description
        formula: Calculation formula
        pit_enabled: Whether PIT tracking is enabled

    """

    factor_id: str
    name: str
    factor_class: FactorClass
    family: FactorFamily
    description: str
    formula: str
    pit_enabled: bool
    status: str = "active"


# Predefined factor classes
FACTOR_CLASS_FUNDAMENTAL = "fundamental"
FACTOR_CLASS_TECHNICAL = "technical"
FACTOR_CLASS_MACRO = "macro"
FACTOR_CLASS_STATISTICAL = "statistical"

# Predefined factor families
FACTOR_FAMILY_VALUE = "value"
FACTOR_FAMILY_MOMENTUM = "momentum"
FACTOR_FAMILY_QUALITY = "quality"
FACTOR_FAMILY_SIZE = "size"
FACTOR_FAMILY_VOLATILITY = "volatility"


__all__ = [
    "FACTOR_CLASS_FUNDAMENTAL",
    "FACTOR_CLASS_MACRO",
    "FACTOR_CLASS_STATISTICAL",
    "FACTOR_CLASS_TECHNICAL",
    "FACTOR_FAMILY_MOMENTUM",
    "FACTOR_FAMILY_QUALITY",
    "FACTOR_FAMILY_SIZE",
    "FACTOR_FAMILY_VALUE",
    "FACTOR_FAMILY_VOLATILITY",
    "FactorClass",
    "FactorFamily",
    "FactorMetadata",
]
