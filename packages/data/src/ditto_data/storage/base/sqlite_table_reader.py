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
        return self._finalize(pl.DataFrame(rows) if rows else pl.DataFrame(), pit=True)

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
            knowledge_column = self._spec.knowledge_column
            if knowledge_column is not None:
                conditions.append(f"{knowledge_column} <= ?")
                params.append(as_of_date)
            pit_from = self._spec.effective_from_column
            pit_to = self._spec.effective_to_column
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
        return self._finalize(
            pl.DataFrame(rows) if rows else pl.DataFrame(),
            pit=as_of_date is not None,
        )

    def _finalize(self, df: pl.DataFrame, *, pit: bool) -> pl.DataFrame:
        """
        修订收敛 + 输出定序（#628 P4）。

        PIT 查询下，同事实键存在多条可见版本（披露锚不同的修订公告、
        双开区间行）时，收敛到 knowledge 最新（并列取 effective_from
        更晚）的一条，再按构造时的排序键倒序输出，保证同输入读取结果
        确定。非 PIT 读取（无 as_of）不收敛——版本历史按原样返回，
        由消费方按需区分版本（corporate_actions 版本史契约）。
        事实键 = spec.fact_key_columns，缺省 (id, date_column)。
        """
        spec = self._spec
        if not pit or df.is_empty():
            return df
        fact_key = spec.fact_key_columns or (
            (spec.id_column, spec.date_column) if spec.date_column is not None else None
        )
        if fact_key is None:
            return df
        rank_columns = [
            column
            for column in (spec.knowledge_column, spec.effective_from_column)
            if column is not None
        ]
        deduped = df.sort(rank_columns, descending=True).unique(
            subset=list(fact_key),
            keep="first",
            maintain_order=True,
        )
        order_column = spec.order_by_column or spec.date_column
        if order_column is None:
            return deduped.sort(rank_columns, descending=True)
        sort_columns = [order_column, *rank_columns]
        # 去重排序键（order_column 可能已在 rank_columns 中）
        deduped_sort = [
            c for i, c in enumerate(sort_columns) if c not in sort_columns[:i]
        ]
        return deduped.sort(deduped_sort, descending=True)
