"""Data sources for external data ingestion."""

from ditto_data.sources.base import (
    DataSource,
    DataSourceError,
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
    SourceTransformationError,
)
from ditto_data.sources.exchange_transformers import (
    ExchangeTransformer,
    ExchangeTransformers,
)
from ditto_data.sources.normalization import (
    Currency,
    Exchange,
    InstrumentType,
    NormalizationConfig,
)
from ditto_data.sources.source import DataSources
from ditto_data.sources.tushare.tushare_source import TushareSource

__all__ = [
    "Currency",
    "DataSource",
    "DataSourceError",
    "DataSources",
    "Exchange",
    "ExchangeTransformer",
    "ExchangeTransformers",
    "InstrumentType",
    "NormalizationConfig",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceTransformationError",
    "TushareSource",
]
