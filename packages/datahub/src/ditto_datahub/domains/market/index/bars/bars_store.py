"""
Index daily bars storage with year partitioning.

Stores OHLCV daily bar data for indices in Parquet files with year
partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.domains.market.base.bars_store_base import MarketBarsStoreBase


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
    dataset name "market/index/bars". The read() method does not require a
    dataset parameter.

    Inherits all common functionality from MarketBarsStoreBase, eliminating
    ~250 lines of duplicated code.
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

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date"]
