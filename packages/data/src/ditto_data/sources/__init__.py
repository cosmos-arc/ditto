"""Data sources for external data ingestion."""

from ditto_data.sources.base import (
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
from ditto_data.sources.protocols import (
    CapitalFetcher,
    CommodityFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_data.sources.registry import SourceRegistry
from ditto_data.sources.source import DataSources
from ditto_data.sources.tushare.tushare_source import TushareSource

__all__ = [
    "CapitalFetcher",
    "CommodityFetcher",
    "Currency",
    "DataSourceError",
    "DataSources",
    "Exchange",
    "ExchangeTransformer",
    "ExchangeTransformers",
    "FundamentalFetcher",
    "InstrumentType",
    "MacroFetcher",
    "MarketFetcher",
    "MetadataFetcher",
    "NormalizationConfig",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceRegistry",
    "SourceTransformationError",
    "TushareSource",
]
