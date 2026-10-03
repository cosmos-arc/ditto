"""
EtfReferenceObservationWriter - ETF 参考事实观察写入接口.

每行绑定一个来源快照（source_snapshot_id），观察缺失从不由当前
instrument 扩展表推断（读侧合同不变）。
"""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import DataCache, SQLiteClient, logger


class EtfReferenceObservationWriter:
    """ETF 参考事实观察写入器（幂等，绑定来源快照）。"""

    def __init__(self, client: SQLiteClient, cache: DataCache[Any] | None) -> None:
        """
        初始化 EtfReferenceObservationWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 可选缓存管理器.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "EtfReferenceObservationWriter initialized",
            event="etf_reference_writer_init_complete",
        )

    def save_observations(self, rows: list[dict[str, object]]) -> int:
        """
        批量写入观察行（幂等：保留同一快照的首次观察）。

        行要求字段：instrument_id/field/value/unit/observed_on/published_at/
        effective_from/effective_to(可空)/source/source_snapshot_id。

        Args:
            rows: 观察行字典列表.

        Returns:
            写入行数.

        """
        written = 0
        for row in rows:
            self._client.execute(
                """INSERT INTO etf_reference_observation
                (instrument_id, field, value, unit, observed_on, published_at,
                 effective_from, effective_to, source, source_snapshot_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id, field, observed_on, source_snapshot_id)
                DO NOTHING""",
                [
                    row["instrument_id"],
                    row["field"],
                    row["value"],
                    row["unit"],
                    row["observed_on"],
                    row["published_at"],
                    row["effective_from"],
                    row.get("effective_to"),
                    row["source"],
                    row["source_snapshot_id"],
                ],
            )
            written += 1
        if written:
            self._client.commit()
            if self._cache is not None:
                self._cache.invalidate_pattern("etf_reference_observation:*")
        logger.info(
            "ETF reference observations saved",
            event="etf_reference_observations_saved",
            rows=written,
        )
        return written
