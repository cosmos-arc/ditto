"""摄取流程共享类型 — SourceFetchers."""

from typing import NamedTuple

from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)

__all__ = ["SourceFetchers"]


class SourceFetchers(NamedTuple):
    """5 个域级 Fetcher Protocol 聚合."""

    metadata: MetadataFetcher
    market: MarketFetcher
    fundamental: FundamentalFetcher
    capital: CapitalFetcher
    macro: MacroFetcher
