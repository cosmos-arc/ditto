"""Index composition reader — 指数权重观察事实读取."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class IndexCompositionReader:
    """
    按观察事实读取指数权重快照.

    #452: index_weight 表存月度权重观察行（trade_date 为观察日）。as-of 语义 =
    截至该日已入库的最近一次观察快照（MAX(trade_date) <= as_of）。官方不提供
    成分调整的公告/生效时刻，本读取器不声称生效区间；发布可知性由摄取侧的
    provider snapshot 证据链承载。
    """

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        self._spec = spec
        self._client = client
        cols = ", ".join(spec.all_columns)
        date_column = spec.date_column
        if date_column is None:
            raise ValueError("index_weight spec requires date_column")
        order_column = spec.order_by_column or "instrument_id"
        self._sql = (
            f"SELECT {cols} "  # noqa: S608
            f"FROM {spec.table} "
            f"WHERE {spec.id_column} = ? "
            f"AND {date_column} = ("
            f"SELECT MAX({date_column}) FROM {spec.table} "
            f"WHERE {spec.id_column} = ? AND {date_column} <= ?) "
            f"ORDER BY {order_column}"
        )

    def get(self, id_value: int | str, as_of_date: date) -> pl.DataFrame:
        """返回截至 as_of 已入库的最近一次观察快照."""
        rows = self._client.fetchall(self._sql, [id_value, id_value, as_of_date])
        return pl.DataFrame(rows) if rows else pl.DataFrame()
