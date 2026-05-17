"""时间上下文 — PIT 语义的统一值对象."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

__all__ = ["TimeContext"]


@dataclass(frozen=True)
class TimeContext:
    """
    时间上下文 — PIT 语义的统一值对象.

    是 Synchronizer 与各包沟通「当前时间」的唯一入口。
    替代散布在 data/helpers/pit/、backtest/data_feed.py 中的分散 PIT 模式。

    Attributes:
        decision_time: 决策时刻（Clock.now() 的语义等价物）
        knowledge_date: 数据可见边界（knowledge_date 之前的行才可见）
        trade_date: 当前交易日（YYYY-MM-DD）

    """

    decision_time: datetime
    knowledge_date: date
    trade_date: str

    @property
    def pit_cutoff(self) -> datetime:
        """PIT 查询的严格上界（不含 knowledge_date 当日数据）."""
        return datetime.combine(self.knowledge_date, time.min)
