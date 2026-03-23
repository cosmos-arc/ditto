"""
PIT (Point-in-Time) Reader / Writer 基类.

TradingRuleReader 与 FeeScheduleReader 共享相同的 PIT 查询逻辑,
差异仅在 Record 类型. 本模块将其提取为泛型基类, 消除重复.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["PITRecord", "PITRecordReader", "PITRecordWriter"]


class PITRecord(Protocol):
    """
    PIT 版本化记录的结构协议.

    所有 PIT Record 必须提供:
        instrument_id: 标的 ID.
        effective_from: 版本生效日期（含）.
        effective_to: 版本失效日期（不含）, NULL 表示当前版本.
    """

    @property
    def instrument_id(self) -> str: ...

    @property
    def effective_from(self) -> str: ...

    @property
    def effective_to(self) -> str | None: ...


class PITRecordReader[RecordT: PITRecord]:
    """PIT 版本化查询 Reader. V1 内存实现."""

    def __init__(self) -> None:
        self._records: list[RecordT] = []

    def load(self, records: list[RecordT]) -> None:
        """加载记录列表（V1 内存实现）."""
        self._records = list(records)

    def get(self, instrument_id: str, as_of_date: str) -> RecordT | None:
        """
        PIT 查询: 获取指定标的在 as_of_date 时有效的记录.

        查询条件:
            effective_from <= as_of_date
            AND (effective_to IS NULL OR effective_to > as_of_date)

        多个版本匹配时，返回 effective_from 最大的版本.
        """
        candidates = [
            r
            for r in self._records
            if r.instrument_id == instrument_id
            and r.effective_from <= as_of_date
            and (r.effective_to is None or r.effective_to > as_of_date)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.effective_from)


class PITRecordWriter[RecordT: PITRecord]:
    """PIT 版本化写入 Writer. V1 内存实现."""

    def __init__(self) -> None:
        self._records: list[RecordT] = []

    def write(self, record: RecordT) -> None:
        """写入一条记录."""
        self._records.append(record)

    def get_records(self) -> list[RecordT]:
        """获取所有已写入的记录（副本）."""
        return list(self._records)
