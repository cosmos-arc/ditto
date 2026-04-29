"""FeeScheduleReader -- PIT 版本化费率查询."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ditto_infra.foundation import SQLitePool
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_data.storage.metadata._pit_base import PITRecordReader

InstrumentId = _InstrumentId

__all__ = ["FeeScheduleReader", "FeeScheduleRecord", "SQLiteFeeScheduleReader"]

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

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

    def list_all(self) -> list[FeeScheduleRecord]:
        """获取所有费率记录."""
        conn = self._pool.get_connection()
        rows = conn.execute(_SELECT_ALL).fetchall()
        return [self._row_to_record(row) for row in rows]

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
