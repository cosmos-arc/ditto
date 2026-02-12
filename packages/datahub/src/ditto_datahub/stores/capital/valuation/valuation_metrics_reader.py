"""ValuationMetrics reader for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class ValuationMetricsReader:
    """估值指标数据读取器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 ValuationMetricsReader.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.valuation_metrics_query")
    def get(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """
        查询估值指标数据（PIT 查询）.

        Args:
            instrument_id: 证券标识符.
            as_of_date: 时间点查询日期.

        Returns:
            估值指标数据 DataFrame，无数据时返回空 DataFrame.

        """
        rows = self._client.fetchall(
            """SELECT instrument_id, trade_date, knowledge_date,
                      effective_from, effective_to,
                      pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap
               FROM valuation_metrics
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY trade_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
