"""
ETF net asset value (NAV) storage with year partitioning.

Stores net asset value data for ETFs in Parquet files with year
partitioning. Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

from ditto_datahub.stores.parquet_store_base import ParquetStoreBase


class EtfNavStore(ParquetStoreBase):
    """
    ETF net asset value data storage with year partitioning.

    Storage structure:
        data_root/
            market/etf/nav/
                2020.parquet
                2021.parquet
                ...

    This store is specialized for ETF NAV and uses a fixed
    dataset name "market/etf/nav".

    Inherits all read/write/metadata operations from ParquetStoreBase.
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize EtfNavStore.

        Args:
            data_root: Root directory for data storage.

        """
        super().__init__(data_root)
        self._dataset = "market/etf/nav"

    # ============ Required abstract method implementations ============

    def _get_dataset(self) -> str:
        """Return dataset name for ETF NAV."""
        return "market/etf/nav"

    def _get_key_columns(self) -> list[str]:
        """Return key column names for deduplication."""
        return ["sid", "trade_date"]
