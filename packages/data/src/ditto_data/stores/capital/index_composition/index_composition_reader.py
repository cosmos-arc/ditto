"""Index composition reader for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import traced

from ditto_data.stores.sqlite_client import SQLiteClient


class IndexCompositionReader:
    """指数成分股数据读取器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 IndexCompositionReader.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.index_composition_query")
    def get(self, index_id: str, as_of_date: date) -> pl.DataFrame:
        """
        查询指数成分股数据（PIT 查询）.

        Args:
            index_id: 指数标识符.
            as_of_date: 时间点查询日期.

        Returns:
            指数成分股数据 DataFrame，无数据时返回空 DataFrame.

        """
        rows = self._client.fetchall(
            """SELECT index_id, instrument_id, weight, effective_from, effective_to
               FROM index_composition
               WHERE index_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY instrument_id""",
            [index_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
