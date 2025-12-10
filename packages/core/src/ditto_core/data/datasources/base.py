"""Base class for data sources."""

from abc import ABC, abstractmethod
from typing import Any

import polars as pl


class DataSource(ABC):
    """Abstract base class for all data sources."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize data source.

        Args:
            config: Configuration dictionary for the data source

        """
        self.config = config or {}
        self.source_type = self._get_source_type()

    @abstractmethod
    def _get_source_type(self) -> str:
        """Get the data source type constant."""
        pass

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the data source."""
        pass

    @abstractmethod
    def get_etf_list(self) -> pl.DataFrame:
        """Get list of available ETFs."""
        pass

    @abstractmethod
    def get_daily_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Get daily price data for a symbol."""
        pass
