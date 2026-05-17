"""ParquetDatasetWriter base class — generic Parquet dataset writer via composition."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import polars as pl
from ditto_platform.foundation import OnDuplicate, ParquetStore, WriteStoreResult

INSTRUMENT_ID_COLUMN = "instrument_id"


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
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """删除数据。"""
        store_filters = [
            *self._instrument_filters(instrument_ids),
            *self._normalize_filters(filters),
        ]
        return self._store.delete(
            self._dataset,
            start_date=start_date,
            end_date=end_date,
            filters=store_filters,
        )

    def delete_partition(self, partition_key: str) -> bool:
        """删除分区。"""
        return self._store.delete_partition(self._dataset, partition_key)

    def _instrument_filters(self, instrument_ids: list[int] | None) -> list[pl.Expr]:
        """构造工具 ID 过滤表达式。"""
        if not instrument_ids:
            return []
        return [pl.col(INSTRUMENT_ID_COLUMN).is_in(instrument_ids)]

    def _normalize_filters(
        self,
        filters: pl.Expr | Sequence[pl.Expr] | None,
    ) -> list[pl.Expr]:
        """规范化额外过滤表达式。"""
        if filters is None:
            return []
        if isinstance(filters, pl.Expr):
            return [filters]
        return list(filters)
