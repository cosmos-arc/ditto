"""Storage layer Protocol definitions for Reader/Writer interfaces."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import polars as pl

from ditto_data.models import OnDuplicate
from ditto_data.models.storage import WriteStoreResult


class DatasetReader(Protocol):
    """Parquet 数据集读取接口。"""

    def read(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame: ...

    def count(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int: ...

    def get_years(self) -> list[int]: ...

    def get_date_range(self) -> tuple[str | None, str | None]: ...

    def get_checksum(self, partition_key: str) -> str: ...

    def list_instrument_ids(self) -> list[int]: ...


class DatasetWriter(Protocol):
    """Parquet 数据集写入接口。"""

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult: ...

    def delete(
        self,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int: ...

    def delete_partition(self, partition_key: str) -> bool: ...


class SqliteReader(Protocol):
    """SQLite 表读取接口（PIT 查询）。"""

    def get(self, id_value: int, as_of_date: date) -> pl.DataFrame: ...


class SqliteWriter(Protocol):
    """SQLite 表写入接口。"""

    def write(self, df: pl.DataFrame) -> int: ...
