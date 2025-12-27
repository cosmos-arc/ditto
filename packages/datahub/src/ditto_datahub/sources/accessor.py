"""SourcesAccessor for DataHub integration."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from ditto_foundation import logger

from ditto_datahub.sources.base import DataSource, get_source

if TYPE_CHECKING:
    pass


class SourcesAccessor:
    """
    Accessor for external data sources.

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
        return get_source("tushare")

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
        return get_source(name)
