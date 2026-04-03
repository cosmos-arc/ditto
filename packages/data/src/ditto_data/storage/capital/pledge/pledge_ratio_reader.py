"""PledgeRatio reader for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import traced

from ditto_data.storage.sqlite_client import SQLiteClient


class PledgeRatioReader:
    """股权质押数据读取器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 PledgeRatioReader.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.pledge_ratio_query")
    def get(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        查询股权质押数据（PIT 查询）.

        Args:
            instrument_id: 证券标识符.
            as_of_date: 时间点查询日期.

        Returns:
            股权质押数据 DataFrame，无数据时返回空 DataFrame.

        """
        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      pledge_ratio, pledge_shares, total_shares
               FROM pledge_ratio
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
