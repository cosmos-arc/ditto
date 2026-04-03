"""
Re-exported domain types for interface layer consumption.

These types are re-exported from ditto_data so that the interfaces layer
does not need to import from ditto_data directly.
"""

from ditto_data.errors import (
    AmbiguousTickerError,
    IdentifierNotFoundError,
    NoIdentifierProvidedError,
)
from ditto_data.models import Dataset, MacroCategory, MacroFrequency
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionResult,
    InstrumentIngestParams,
    ResultCounts,
    RetryResult,
)
from ditto_data.quality import QualityEngine
from ditto_data.quality.spec import DQIssue, DQResult

__all__ = [
    "AmbiguousTickerError",
    "BackfillResult",
    "DQIssue",
    "DQResult",
    "Dataset",
    "IdentifierNotFoundError",
    "IngestionResult",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroFrequency",
    "NoIdentifierProvidedError",
    "QualityEngine",
    "ResultCounts",
    "RetryResult",
]
