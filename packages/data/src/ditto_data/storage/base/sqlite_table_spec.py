"""SqliteTableSpec — frozen dataclass for parameterizing SQLite table structure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqliteTableSpec:
    """SQLite 表查询规格，参数化表结构差异。"""

    table: str
    columns: tuple[str, ...]
    id_column: str
    date_column: str | None = None
    nullable_columns: frozenset[str] = frozenset()
    pit_columns: tuple[str, ...] = ("knowledge_date", "effective_from", "effective_to")
    order_by_column: str | None = None

    @property
    def all_columns(self) -> tuple[str, ...]:
        """完整列集：id + date + pit + business columns。"""
        cols: tuple[str, ...] = (self.id_column,)
        if self.date_column:
            cols = (*cols, self.date_column)
        return (*cols, *self.pit_columns, *self.columns)
