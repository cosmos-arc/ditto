"""ValuationMetrics writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class ValuationMetricsWriter:
    """估值指标数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """
        初始化 ValuationMetricsWriter.

        Args:
            client: SQLite 客户端实例.

        """
        self._client = client

    @traced("data.valuation_metrics_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        写入估值指标数据.

        Args:
            df: 估值指标数据 DataFrame.

        Returns:
            写入的记录数.

        Raises:
            Exception: 写入失败时传播异常.

        """
        logger.info("Starting valuation metrics data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO valuation_metrics
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("pe_ratio"),
                        r.get("pb_ratio"),
                        r.get("ps_ratio"),
                        r.get("dividend_yield"),
                        r.get("market_cap"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Valuation metrics data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "valuation_metrics", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Valuation metrics write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "valuation_metrics", "status": "failed"}
            )
            raise
