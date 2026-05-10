"""
BacktestSynchronizer — 回测时间同步器.

封装 DataFeed + SimulatedClock，日历驱动迭代。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from ditto_kernel.clock import Clock, SimulatedClock
from ditto_kernel.synchronizer import TimeSlice
from ditto_kernel.time_context import TimeContext

from ditto_backtest.data_feed import DataFeed

__all__ = ["BacktestSynchronizer"]


class BacktestSynchronizer:
    """
    回测时间同步器 — 将 DataFeed 桥接为 Synchronizer Protocol 的 TimeSlice 流.

    时钟由外部推进（EngineLoop 负责 advance_to），本类仅持有引用。
    """

    def __init__(
        self,
        data_feed: DataFeed,
        clock: SimulatedClock,
        start_date: str,
        knowledge_lag_days: int = 1,
    ) -> None:
        self._feed = data_feed
        self._clock = clock
        self._start_date = start_date
        self._knowledge_lag_days = knowledge_lag_days

    def stream(self) -> Iterator[TimeSlice]:
        """产生时间切片流 — 回测时有限，实盘时无限."""
        for date_str in self._feed.trading_days():
            # Synchronizer 过滤: 控制迭代范围（决定产出哪些 TimeSlice）
            # EngineLoop 也按 start_date 过滤 trading_days（用于 is_rebalance_day 索引）
            if date_str < self._start_date:
                continue
            slice_ = self._feed.get_slice(date_str)
            tc = TimeContext(
                decision_time=slice_.step_time,
                knowledge_date=slice_.step_time.date()
                - timedelta(days=self._knowledge_lag_days),
                trade_date=slice_.trade_date,
            )
            yield TimeSlice(time_context=tc, bars=slice_.bars)

    def clock(self) -> Clock:
        """返回与此同步器关联的时钟."""
        return self._clock
