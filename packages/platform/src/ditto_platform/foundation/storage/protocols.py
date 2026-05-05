"""Storage layer Protocol definitions for Reader/Writer interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol

import polars as pl

from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult


class DatasetReader(Protocol):
    """Parquet dataset read interface."""

    def read(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> pl.DataFrame:
        """Read data from dataset."""
        ...

    def count(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """Count records in dataset."""
        ...

    def get_years(self) -> list[int]:
        """Get available years."""
        ...

    def get_date_range(self) -> tuple[str | None, str | None]:
        """Get date range of dataset."""
        ...

    def get_checksum(self, partition_key: str) -> str:
        """Get checksum for partition."""
        ...

    def list_unique_values(self, column: str) -> list[Any]:
        """List unique values for a column."""
        ...


class DatasetWriter(Protocol):
    """Parquet dataset write interface."""

    def write(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteStoreResult:
        """Write data to dataset."""
        ...

    def delete(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: pl.Expr | Sequence[pl.Expr] | None = None,
    ) -> int:
        """Delete data from dataset."""
        ...

    def delete_partition(self, partition_key: str) -> bool:
        """Delete a partition."""
        ...


class SqliteReader(Protocol):
    """SQLite table read interface (PIT queries)."""

    def get(self, id_value: int, as_of_date: date) -> pl.DataFrame:
        """Get record by ID and date."""
        ...


class SqliteWriter(Protocol):
    """SQLite table write interface."""

    def write(self, df: pl.DataFrame) -> int:
        """Write DataFrame to table."""
        ...
