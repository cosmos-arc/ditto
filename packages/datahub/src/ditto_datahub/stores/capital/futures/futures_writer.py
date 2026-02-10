"""Futures writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FuturesWriter:
    """期货数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 FuturesWriter.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.futures_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        写入期货数据.

        Args:
            df: 期货数据 DataFrame.

        Returns:
            写入的记录数.

        Raises:
            Exception: 写入失败时传播异常.

        """
        logger.info("Starting futures data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO futures
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 open_interest, settlement_price, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("open_interest"),
                        r.get("settlement_price"),
                        r.get("volume"),
                        r.get("turnover"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Futures data written successfully", record_count=len(records))
            M.data_records.add(
                len(records), {"dataset": "futures", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Futures write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "futures", "status": "failed"})
            raise
