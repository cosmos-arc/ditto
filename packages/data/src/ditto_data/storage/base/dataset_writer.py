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
        """
        写入数据（跨年分片 + 同年文件锁统一在此收口）。

        行按存储声明的 date_column 年分片落各自年分区（锚年单分区写会
        让跨年帧中非锚年的行对该年有界读不可见，#629 E1/#627 F1 先例，
        审计 #684 批B #14）；每个年分区写入以 ``{dataset}_write_{year}``
        文件锁串行化（backfill --parallel 并发写同年分区的丢失更新防护，
        审计 #684 批B #7）。空帧保持锚年单分区写（分区登记语义不变）。
        多分片时返回的 added/updated/skipped/is_merge 为聚合值，
        file_path/checksum 取最后一个分片。
        """
        aggregate = WriteStoreResult(
            file_path="", checksum="", added=0, updated=0, skipped=0, is_merge=False
        )
        for part_year, part in self._year_shards(df, year):
            shard = self._write_locked(part, part_year, on_duplicate)
            aggregate = WriteStoreResult(
                file_path=shard.file_path,
                checksum=shard.checksum,
                added=aggregate.added + shard.added,
                updated=aggregate.updated + shard.updated,
                skipped=aggregate.skipped + shard.skipped,
                is_merge=aggregate.is_merge or shard.is_merge,
            )
        return aggregate

    def _write_locked(
        self,
        part: pl.DataFrame,
        part_year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteStoreResult:
        """单年分区写入，携带 store 的文件锁时按统一锁名串行。"""
        store = self._store
        if store.file_lock is None:
            return store.write(self._dataset, part, on_duplicate.value, year=part_year)
        lock_name = f"{self._dataset}_write_{part_year}".replace("/", "_")
        with store.file_lock.acquire(lock_name, timeout=60.0):
            return store.write(self._dataset, part, on_duplicate.value, year=part_year)

    def _year_shards(
        self, df: pl.DataFrame, anchor_year: int
    ) -> list[tuple[int, pl.DataFrame]]:
        """按 date_column 年切分帧；空帧或未声明日期轴时退化为锚年单分片。"""
        date_column = self._store.date_column
        if df.height == 0 or date_column is None:
            return [(anchor_year, df)]
        if date_column not in df.columns:
            # 声明了分区锚却缺列 = 帧与存储 schema 脱节，锚年单写会静默
            # 错置分区——fail closed（与 null 锚同律）。
            msg = (
                f"cannot shard {self._dataset}: declared date column "
                f"{date_column!r} missing from frame"
            )
            raise ValueError(msg)
        if df[date_column].is_null().any():
            msg = (
                f"cannot shard {self._dataset}: column {date_column!r} has nulls "
                "(partition anchor must be non-null)"
            )
            raise ValueError(msg)
        year_expr = pl.col(date_column).cast(pl.Date).dt.year()
        years = sorted(set(df.select(year_expr.alias("_year"))["_year"].to_list()))
        return [(y, df.filter(year_expr == y)) for y in years]

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
