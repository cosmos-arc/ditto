"""FeeScheduleWriter -- PIT 版本化费率写入."""

from __future__ import annotations

from ditto_datahub.stores.metadata._pit_base import PITRecordWriter
from ditto_datahub.stores.metadata.fee_schedule_reader import FeeScheduleRecord

__all__ = ["FeeScheduleWriter"]


class FeeScheduleWriter(PITRecordWriter[FeeScheduleRecord]):
    """费率 Writer. V1 内存实现."""
