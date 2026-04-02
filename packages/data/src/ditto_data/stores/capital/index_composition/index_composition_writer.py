"""Index composition writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_data.stores.sqlite_client import SQLiteClient


class IndexCompositionWriter:
    """指数成分股数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 IndexCompositionWriter.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.index_composition_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        写入指数成分股数据.

        Args:
            df: 指数成分股数据 DataFrame.

        Returns:
            写入的记录数.

        Raises:
            Exception: 写入失败时传播异常.

        """
        logger.info("Starting index composition data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO index_composition
                (index_id, instrument_id, weight, effective_from, effective_to)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["index_id"],
                        r["instrument_id"],
                        r.get("weight"),
                        r["effective_from"],
                        r.get("effective_to"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Index composition data written successfully", record_count=len(records)
            )
            Metrics.data_records.add(
                len(records), {"dataset": "index_composition", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Index composition write failed", error=str(e))
            Metrics.data_records.add(
                len(df), {"dataset": "index_composition", "status": "failed"}
            )
            raise
