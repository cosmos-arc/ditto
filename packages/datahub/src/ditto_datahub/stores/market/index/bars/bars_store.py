"""
Index daily bars storage with year partitioning.

Stores OHLCV daily bar data for indices in Parquet files with year
partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.stores.market.base.bars_store_base import MarketBarsStoreBase


class IndexBarsStore(MarketBarsStoreBase):
    """
    Index daily bars data storage with year partitioning.

    Storage structure:
        data_root/
            market/index/bars/
                2020.parquet
                2021.parquet
                ...

    This store is specialized for index daily bars and uses a fixed
    dataset name "market/index/bars". All read/write operations are
    delegated to ParquetStore via MarketBarsStoreBase.

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize IndexBarsStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "market/index/bars"

    def _get_dataset(self) -> str:
        """Return dataset name for index bars."""
        return "market/index/bars"
