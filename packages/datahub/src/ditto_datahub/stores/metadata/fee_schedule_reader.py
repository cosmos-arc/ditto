"""FeeScheduleReader -- PIT 版本化费率查询."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_datahub.stores.metadata._pit_base import PITRecordReader

__all__ = ["FeeScheduleReader", "FeeScheduleRecord"]


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

    instrument_id: str
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    effective_from: str
    effective_to: str | None = None


class FeeScheduleReader(PITRecordReader[FeeScheduleRecord]):
    """费率 Reader -- PIT 版本化查询. V1 内存实现."""
