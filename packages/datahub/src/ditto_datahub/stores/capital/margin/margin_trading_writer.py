"""Margin trading writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class MarginTradingWriter:
    """融资融券数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 MarginTradingWriter.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.margin_trading_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        写入融资融券数据.

        Args:
            df: 融资融券数据 DataFrame.

        Returns:
            写入的记录数.

        Raises:
            Exception: 写入失败时传播异常.

        """
        logger.info("Starting margin trading data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO margin_trading
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 margin_buy_balance, short_sell_balance,
                 margin_buy_volume, short_sell_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("margin_buy_balance"),
                        r.get("short_sell_balance"),
                        r.get("margin_buy_volume"),
                        r.get("short_sell_volume"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Margin trading data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "margin_trading", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Margin trading write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "margin_trading", "status": "failed"}
            )
            raise
