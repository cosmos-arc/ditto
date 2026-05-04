"""ParquetDatasetReader base class — generic Parquet dataset reader via composition."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_platform.foundation.storage import ParquetStore


class ParquetDatasetReader:
    """通用 Parquet 数据集读取器，通过 dataset 路径参数化。"""

    def __init__(self, store: ParquetStore, dataset: str) -> None:
        self._store = store
        self._dataset = dataset

    @property
    def data_root(self) -> Path:
        """数据根目录。"""
        return self._store.data_root

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """读取数据。"""
        return self._store.read(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """统计记录数。"""
        return self._store.count(
            self._dataset,
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_years(self) -> list[int]:
        """获取可用年份列表。"""
        return self._store.get_years(self._dataset)

    def get_date_range(self) -> tuple[str | None, str | None]:
        """获取数据集日期范围。"""
        return self._store.get_date_range(self._dataset)

    def get_checksum(self, partition_key: str) -> str:
        """获取分区校验和。"""
        return self._store.get_checksum(self._dataset, partition_key)

    def list_instrument_ids(self) -> list[int]:
        """列出所有工具 ID。"""
        return self._store.list_instrument_ids(self._dataset)
