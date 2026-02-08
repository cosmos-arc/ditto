"""Macro domain - macro economic indicator data storage."""

from ditto_datahub.stores.macro.indicator import (
    IndicatorMetadataStore,
    IndicatorStore,
)

__all__ = [
    "IndicatorMetadataStore",
    "IndicatorStore",
]
