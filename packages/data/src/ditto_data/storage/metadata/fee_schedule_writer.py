"""FeeScheduleWriter -- PIT 版本化费率写入."""

from __future__ import annotations

from ditto_infra.foundation import SQLitePool, logger, traced

from ditto_data.storage.metadata._pit_base import PITRecordWriter
from ditto_data.storage.metadata.fee_schedule_reader import FeeScheduleRecord

__all__ = ["FeeScheduleWriter", "SQLiteFeeScheduleWriter"]

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


class FeeScheduleWriter(PITRecordWriter[FeeScheduleRecord]):
    """费率 Writer. V1 内存实现."""


class SQLiteFeeScheduleWriter(PITRecordWriter[FeeScheduleRecord]):
    """费率 Writer -- SQLite PIT 版本化写入."""

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

    def write(self, record: FeeScheduleRecord) -> None:
        """写入一条记录（INSERT OR REPLACE）。"""
        conn = self._pool.get_connection()
        conn.execute(
            _INSERT_OR_REPLACE,
            (
                record.instrument_id,
                record.as_of_date,
                record.commission_rate,
                record.min_commission,
                record.stamp_duty_rate,
                record.transfer_fee_rate,
                record.effective_from,
                record.effective_to,
            ),
        )
        self._pool.commit()

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
