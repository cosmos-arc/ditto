"""SourcesProvider for DataHub integration."""

from __future__ import annotations

from functools import cached_property

from ditto_foundation import logger

from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare.source import TushareSource


class SourcesProvider:
    """
    Provider for external data sources.

    Provides convenient access to DataSource instances with caching.

    """

    @cached_property
    def tushare(self) -> DataSource:
        """
        Get Tushare data source.

        Returns:
            TushareSource instance.

        """
        logger.debug("Creating TushareSource", event="sources_tushare_create")
        return TushareSource()

    def get(self, name: str) -> DataSource:
        """
        Get data source by name.

        Args:
            name: Source name (e.g., "tushare", "akshare").

        Returns:
            DataSource instance.

        Raises:
            ValueError: If source name is unknown.

        """
        normalized_name = name.lower().strip()

        if normalized_name == "tushare":
            return TushareSource()

        raise ValueError(f"Unknown source: '{name}'. Supported sources: tushare")
