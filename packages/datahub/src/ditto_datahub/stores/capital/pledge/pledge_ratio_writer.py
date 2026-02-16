"""PledgeRatio writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class PledgeRatioWriter:
    """股权质押数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 PledgeRatioWriter.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.pledge_ratio_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        写入股权质押数据.

        Args:
            df: 股权质押数据 DataFrame.

        Returns:
            写入的记录数.

        Raises:
            Exception: 写入失败时传播异常.

        """
        logger.info("Starting pledge ratio data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO pledge_ratio
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 pledge_ratio, pledge_shares, total_shares)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("pledge_ratio"),
                        r.get("pledge_shares"),
                        r.get("total_shares"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Pledge ratio data written successfully", record_count=len(records)
            )
            Metrics.data_records.add(
                len(records), {"dataset": "pledge_ratio", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Pledge ratio write failed", error=str(e))
            Metrics.data_records.add(
                len(df), {"dataset": "pledge_ratio", "status": "failed"}
            )
            raise
