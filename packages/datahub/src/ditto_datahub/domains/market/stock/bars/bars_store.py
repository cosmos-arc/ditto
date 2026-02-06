"""
Stock daily bars storage with year partitioning.

Stores OHLCV daily bar data for stocks in Parquet files with year
partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.domains.market.base.bars_store_base import MarketBarsStoreBase


class StockBarsStore(MarketBarsStoreBase):
    """
    Stock daily bars data storage with year partitioning.

    Storage structure:
        data_root/
            market/stock/bars/
                2020.parquet
                2021.parquet
                ...

    This store is specialized for stock daily bars and uses a fixed
    dataset name "market/stock/bars". All read/write operations are
    delegated to ParquetStore via MarketBarsStoreBase.

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize StockBarsStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "market/stock/bars"

    def _get_dataset(self) -> str:
        """Return dataset name for stock bars."""
        return "market/stock/bars"
