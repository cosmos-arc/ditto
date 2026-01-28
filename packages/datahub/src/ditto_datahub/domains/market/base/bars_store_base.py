"""
Base class for Market domain Bars stores.

Provides common functionality for all market bars stores (Stock/ETF/Index),
eliminating code duplication across these domain-specific stores.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class MarketBarsStoreBase(ParquetStoreBase):
    """
    Base class for market domain Bars stores.

    This class provides a common implementation for all market bars stores
    (Stock/ETF/Index). The base ParquetStoreBase now provides complete
    implementations for read(), write(), and all metadata operations.

    Subclasses only need to:
    1. Implement _get_dataset() to return their dataset name
    2. Implement _get_key_columns() to return key columns for deduplication

    Storage structure:
        data_root/
            market/{asset_class}/bars/
                2020.parquet
                2021.parquet
                ...

    Example:
        class StockBarsStore(MarketBarsStoreBase):
            def __init__(self, data_root: Path) -> None:
                super().__init__(data_root)
                self._dataset = "market/stock/bars"

            def _get_dataset(self) -> str:
                return "market/stock/bars"

            def _get_key_columns(self) -> list[str]:
                return ["sid", "trade_date"]

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize MarketBarsStoreBase.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        # Subclass must set self._dataset in their __init__
        self._dataset: str

    # ============ Abstract methods (must be implemented by subclasses) ============

    @abstractmethod
    def _get_dataset(self) -> str:
        """
        Get dataset name for this store.

        Returns:
            Dataset name (e.g., "market/stock/bars").

        """
        ...
