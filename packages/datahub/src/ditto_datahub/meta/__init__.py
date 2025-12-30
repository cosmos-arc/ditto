"""
Metadata layer for DataHub.

This module contains schema definitions and other metadata used across
the DataHub package.
"""

from ditto_datahub.meta.schemas import (
    ADJ_FACTOR_SCHEMA,
    ETF_DAILY_SCHEMA,
    INDEX_DAILY_SCHEMA,
    INDEX_WEIGHT_SCHEMA,
    STOCK_DAILY_SCHEMA,
    STOCK_STATUS_SCHEMA,  # B.3: Stock status schema
    UNIVERSE_CONSTITUENT_SCHEMA,
)

__all__ = [
    "ADJ_FACTOR_SCHEMA",
    "ETF_DAILY_SCHEMA",
    "INDEX_DAILY_SCHEMA",
    "INDEX_WEIGHT_SCHEMA",
    "STOCK_DAILY_SCHEMA",
    "STOCK_STATUS_SCHEMA",
    "UNIVERSE_CONSTITUENT_SCHEMA",
]
