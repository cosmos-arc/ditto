"""
Base client for data source integration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl


@dataclass
class EtfInfo:
    """ETF basic information."""

    ts_code: str
    symbol: str
    name: str
    manager: str
    establish_date: date
    list_date: date
    fund_type: str


class BaseClient(ABC):
    """Abstract base class for data source clients."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize client with configuration."""
        self.config = config or {}

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    def get_etf_list(self) -> list[EtfInfo]:
        """Get list of available ETFs."""
        pass

    @abstractmethod
    def get_daily_data(
        self, ts_code: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """Get daily market data."""
        pass

    @abstractmethod
    def validate_data_quality(self, ts_code: str) -> dict[str, Any]:
        """Validate data quality for a given symbol."""
        pass
