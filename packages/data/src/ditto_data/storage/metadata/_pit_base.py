"""
PIT (Point-in-Time) Reader / Writer 基类.

TradingRuleReader 与 FeeScheduleReader 共享相同的 PIT 查询逻辑,
差异仅在 Record 类型. 本模块将其提取为泛型基类, 消除重复.
"""

from __future__ import annotations

from typing import Protocol

from ditto_kernel.identity import InstrumentId as _InstrumentId

InstrumentId = _InstrumentId

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
    def instrument_id(self) -> InstrumentId: ...

    @property
    def effective_from(self) -> str: ...

    @property
    def effective_to(self) -> str | None: ...


class PITRecordReader[RecordT: PITRecord]:
    """PIT 版本化查询 Reader. V1 内存实现."""

    def __init__(self, backing_store: list[RecordT] | None = None) -> None:
        self._store: list[RecordT] = backing_store if backing_store is not None else []

    @property
    def backing_store(self) -> list[RecordT]:
        """底层存储引用（用于配套 Writer 共享同一存储）."""
        return self._store

    def get(self, instrument_id: InstrumentId, as_of_date: str) -> RecordT | None:
        """
        PIT 查询: 获取指定标的在 as_of_date 时有效的记录.

        查询条件:
            effective_from <= as_of_date
            AND (effective_to IS NULL OR effective_to > as_of_date)

        多个版本匹配时，返回 effective_from 最大的版本.
        """
        candidates = [
            r
            for r in self._store
            if r.instrument_id == instrument_id
            and r.effective_from <= as_of_date
            and (r.effective_to is None or r.effective_to > as_of_date)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.effective_from)


class PITRecordWriter[RecordT: PITRecord]:
    """PIT 版本化写入 Writer. V1 内存实现."""

    def __init__(self, backing_store: list[RecordT] | None = None) -> None:
        self._store: list[RecordT] = backing_store if backing_store is not None else []

    def write(self, record: RecordT) -> None:
        """写入一条记录."""
        self._store.append(record)

    def _get_records(self) -> list[RecordT]:
        """获取所有已写入的记录（内部接口，仅供测试使用）."""
        return list(self._store)
