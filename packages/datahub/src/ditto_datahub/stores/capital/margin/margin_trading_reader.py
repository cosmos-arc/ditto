"""Margin trading reader for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class MarginTradingReader:
    """融资融券数据读取器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 MarginTradingReader.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.margin_trading_query")
    def get(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        查询融资融券数据（PIT 查询）.

        Args:
            instrument_id: 证券标识符.
            as_of_date: 时间点查询日期.

        Returns:
            融资融券数据 DataFrame，无数据时返回空 DataFrame.

        """
        rows = self._client.fetchall(
            """SELECT instrument_id, trade_date, knowledge_date,
                      effective_from, effective_to,
                      margin_buy_balance, short_sell_balance,
                      margin_buy_volume, short_sell_volume
               FROM margin_trading
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY trade_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()
