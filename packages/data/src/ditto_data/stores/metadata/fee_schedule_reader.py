"""FeeScheduleReader -- PIT 版本化费率查询."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ditto_infra.foundation import SQLitePool, logger, traced
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_data.stores.metadata._pit_base import PITRecordReader

InstrumentId = _InstrumentId

__all__ = ["FeeScheduleReader", "FeeScheduleRecord", "SQLiteFeeScheduleReader"]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS fee_schedule (
    instrument_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    commission_rate REAL NOT NULL,
    min_commission REAL NOT NULL,
    stamp_duty_rate REAL NOT NULL,
    transfer_fee_rate REAL NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    PRIMARY KEY (instrument_id, effective_from)
);
"""

_INSERT_OR_REPLACE = """
INSERT OR REPLACE INTO fee_schedule (
    instrument_id, as_of_date, commission_rate, min_commission,
    stamp_duty_rate, transfer_fee_rate, effective_from, effective_to
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_PIT_QUERY = """
SELECT instrument_id, as_of_date, commission_rate, min_commission,
       stamp_duty_rate, transfer_fee_rate, effective_from, effective_to
FROM fee_schedule
WHERE instrument_id = ?
  AND effective_from <= ?
  AND (effective_to IS NULL OR effective_to > ?)
ORDER BY effective_from DESC
LIMIT 1
"""

_SELECT_ALL = """
SELECT instrument_id, as_of_date, commission_rate, min_commission,
       stamp_duty_rate, transfer_fee_rate, effective_from, effective_to
FROM fee_schedule
"""


@dataclass(frozen=True)
class FeeScheduleRecord:
    """
    费率持久化记录（含 PIT 字段）.

    Attributes:
        instrument_id: 标的 ID.
        as_of_date: 规则生效日期 (YYYY-MM-DD).
        commission_rate: 佣金费率.
        min_commission: 最低佣金 (A股=5元).
        stamp_duty_rate: 印花税率 (ETF=0, 股票=0.0005 卖出).
        transfer_fee_rate: 过户费率 (ETF=0, 股票=0.00001).
        effective_from: 版本生效日期（含）.
        effective_to: 版本失效日期（不含）, NULL 表示当前版本.

    """

    instrument_id: InstrumentId
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    effective_from: str
    effective_to: str | None = None


class FeeScheduleReader(PITRecordReader[FeeScheduleRecord]):
    """费率 Reader -- PIT 版本化查询. V1 内存实现."""


class SQLiteFeeScheduleReader(PITRecordReader[FeeScheduleRecord]):
    """费率 Reader -- SQLite PIT 版本化查询."""

    def __init__(self, pool: SQLitePool) -> None:
        self._pool = pool

    @traced("fee_schedule.init_schema")
    def init_schema(self) -> None:
        """创建 fee_schedule 表（幂等操作）。"""
        conn = self._pool.get_connection()
        conn.executescript(_CREATE_TABLE)
        self._pool.commit()
        logger.debug(
            "fee_schedule schema initialized",
            event="fee_schedule_schema_init",
        )

    def load(self, records: list[FeeScheduleRecord]) -> None:
        """批量加载记录到 SQLite（INSERT OR REPLACE）。"""
        if not records:
            return
        conn = self._pool.get_connection()
        for rec in records:
            conn.execute(
                _INSERT_OR_REPLACE,
                (
                    rec.instrument_id,
                    rec.as_of_date,
                    rec.commission_rate,
                    rec.min_commission,
                    rec.stamp_duty_rate,
                    rec.transfer_fee_rate,
                    rec.effective_from,
                    rec.effective_to,
                ),
            )
        self._pool.commit()

    def get(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeScheduleRecord | None:
        """
        PIT 查询: 获取指定标的在 as_of_date 时有效的记录.

        查询条件:
            effective_from <= as_of_date
            AND (effective_to IS NULL OR effective_to > as_of_date)

        多个版本匹配时，返回 effective_from 最大的版本.
        """
        conn = self._pool.get_connection()
        row = conn.execute(
            _PIT_QUERY, (instrument_id, as_of_date, as_of_date)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def _row_to_record(self, row: sqlite3.Row) -> FeeScheduleRecord:
        """将数据库行转换为 FeeScheduleRecord."""
        return FeeScheduleRecord(
            instrument_id=InstrumentId(row["instrument_id"]),
            as_of_date=row["as_of_date"],
            commission_rate=row["commission_rate"],
            min_commission=row["min_commission"],
            stamp_duty_rate=row["stamp_duty_rate"],
            transfer_fee_rate=row["transfer_fee_rate"],
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
        )
