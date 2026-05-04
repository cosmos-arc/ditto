"""ParquetDatasetWriter base class — generic Parquet dataset writer via composition."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_platform.foundation.storage import ParquetStore
from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult


class ParquetDatasetWriter:
    """通用 Parquet 数据集写入器，通过 dataset 路径参数化。"""

    def __init__(self, store: ParquetStore, dataset: str) -> None:
        self._store = store
        self._dataset = dataset

    @property
    def data_root(self) -> Path:
        """数据根目录。"""
        return self._store.data_root

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """写入数据。"""
        return self._store.write(self._dataset, df, on_duplicate.value, year=year)

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """删除数据。"""
        return self._store.delete(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def delete_partition(self, partition_key: str) -> bool:
        """删除分区。"""
        return self._store.delete_partition(self._dataset, partition_key)
