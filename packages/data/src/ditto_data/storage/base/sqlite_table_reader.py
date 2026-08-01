"""SqliteTableReader — 通过 SqliteTableSpec 参数化的通用 SQLite PIT 读取器。"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class SqliteTableReader:
    """通用 SQLite PIT 表读取器，通过 spec 参数化表结构和查询逻辑."""

    _MIN_PIT_COLUMNS = 2
    _KNOWLEDGE_PIT_COLUMNS = 3

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        self._spec = spec
        self._client = client
        if len(spec.pit_columns) < self._MIN_PIT_COLUMNS:
            n = len(spec.pit_columns)
            raise ValueError(f"pit_columns needs >= {self._MIN_PIT_COLUMNS}, got {n}")
        cols = ", ".join(spec.all_columns)
        pit_from = spec.pit_columns[-self._MIN_PIT_COLUMNS]
        pit_to = spec.pit_columns[-1]
        knowledge_clause = (
            f"AND {spec.pit_columns[-self._KNOWLEDGE_PIT_COLUMNS]} <= ? "
            if len(spec.pit_columns) >= self._KNOWLEDGE_PIT_COLUMNS
            else ""
        )
        order_col = spec.order_by_column or spec.date_column
        order_clause = f"ORDER BY {order_col} DESC" if order_col else ""
        self._sql = (
            f"SELECT {cols} "  # noqa: S608
            f"FROM {spec.table} "
            f"WHERE {spec.id_column} = ? "
            f"{knowledge_clause}"
            f"AND {pit_from} <= ? "
            f"AND ({pit_to} IS NULL OR {pit_to} > ?) "
            f"{order_clause}"
        ).rstrip()

    def get(self, id_value: int | str, as_of_date: date) -> pl.DataFrame:
        """PIT 查询：获取指定时间点的有效记录。"""
        params: list[Any] = [id_value]
        if len(self._spec.pit_columns) >= self._KNOWLEDGE_PIT_COLUMNS:
            params.append(as_of_date)
        params.extend((as_of_date, as_of_date))
        rows = self._client.fetchall(self._sql, params)
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def get_range(
        self,
        id_value: int | str,
        start_date: date | None = None,
        end_date: date | None = None,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """日期范围查询 + 可选 PIT 过滤。"""
        conditions = [f"{self._spec.id_column} = ?"]
        params: list[Any] = [id_value]

        if self._spec.date_column and start_date is not None:
            conditions.append(f"{self._spec.date_column} >= ?")
            params.append(start_date)

        if self._spec.date_column and end_date is not None:
            conditions.append(f"{self._spec.date_column} <= ?")
            params.append(end_date)

        if as_of_date is not None:
            if len(self._spec.pit_columns) >= self._KNOWLEDGE_PIT_COLUMNS:
                knowledge_column = self._spec.pit_columns[-self._KNOWLEDGE_PIT_COLUMNS]
                conditions.append(f"{knowledge_column} <= ?")
                params.append(as_of_date)
            pit_from = self._spec.pit_columns[-2]
            pit_to = self._spec.pit_columns[-1]
            conditions.append(f"{pit_from} <= ?")
            params.append(as_of_date)
            conditions.append(f"({pit_to} IS NULL OR {pit_to} > ?)")
            params.append(as_of_date)

        where_clause = f" WHERE {' AND '.join(conditions)}"
        cols = ", ".join(self._spec.all_columns)
        order_col = self._spec.order_by_column or self._spec.date_column
        order_clause = f"ORDER BY {order_col} DESC" if order_col else ""

        sql = (
            f"SELECT {cols} "  # noqa: S608
            f"FROM {self._spec.table}"
            f"{where_clause} "
            f"{order_clause}"
        ).rstrip()

        rows = self._client.fetchall(sql, params)
        return pl.DataFrame(rows) if rows else pl.DataFrame()
