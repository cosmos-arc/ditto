"""ParquetDatasetReader base class — generic Parquet dataset reader via composition."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl
from ditto_platform.foundation import ParquetStore

INSTRUMENT_ID_COLUMN = "instrument_id"


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
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> pl.DataFrame:
        """读取数据。"""
        store_filters = [
            *self._instrument_filters(instrument_ids),
            *self._normalize_filters(filters),
        ]
        return self._store.read(
            self._dataset,
            start_date=start_date,
            end_date=end_date,
            filters=store_filters,
        )

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """统计记录数。"""
        store_filters = [
            *self._instrument_filters(instrument_ids),
            *self._normalize_filters(filters),
        ]
        return self._store.count(
            self._dataset,
            start_date=start_date,
            end_date=end_date,
            filters=store_filters,
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
        values = self.list_unique_values(INSTRUMENT_ID_COLUMN)
        return [int(value) for value in values]

    def list_unique_values(self, column: str) -> list[Any]:
        """列出指定列的唯一值。"""
        return self._store.list_unique_values(self._dataset, column)

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
