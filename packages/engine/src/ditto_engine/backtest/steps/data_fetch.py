"""
DataFetchStep -- 从 DataFeed 获取 Slice + 账户快照 + 清除到期锁定.

对应 EngineLoop._step() 的前半部分:
  1. data_feed.get_slice(date) -> Slice
  2. clock.advance_to(slice.step_time)
  3. brokerage.get_account() -> AccountView
  4. input_instruments.update(slice.bars.keys())
  5. strategy_context.clear_locks(date)
  6. bar_fingerprints 累积 (date, close) 用于数据指纹
"""

from __future__ import annotations

from ditto_kernel.clock import Clock
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext

from ditto_engine.backtest.data_feed import DataFeed
from ditto_engine.backtest.steps.types import StepContext, StepResult
from ditto_engine.execution.brokerage import Brokerage

__all__ = ["DataFetchStep"]


class DataFetchStep:
    """
    数据获取步骤 -- 从 DataFeed 获取 Slice + 账户快照 + 清除到期锁定.

    执行后 ctx.slice_ 和 ctx.account_view 被设置。
    """

    def __init__(
        self,
        data_feed: DataFeed,
        clock: Clock,
        brokerage: Brokerage,
        strategy_context: StrategyContext,
        input_instruments: set[InstrumentId],
        bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
    ) -> None:
        self._data_feed = data_feed
        self._clock = clock
        self._brokerage = brokerage
        self._strategy_context = strategy_context
        self._input_instruments = input_instruments
        self._bar_fingerprints = bar_fingerprints

    def execute(self, ctx: StepContext) -> StepResult:
        """获取当日数据并设置到 StepContext。"""
        slice_ = self._data_feed.get_slice(ctx.date)
        self._clock.advance_to(slice_.step_time)
        account_view = self._brokerage.get_account()

        # 收集输入标的 -- 用于 RunManifest input_refs
        self._input_instruments.update(slice_.bars.keys())

        # 累积 bar 数据指纹 -- (date, close) per instrument
        for iid, bar in slice_.bars.items():
            if iid not in self._bar_fingerprints:
                self._bar_fingerprints[iid] = []
            self._bar_fingerprints[iid].append((ctx.date, bar.close))

        # 每日清除到期锁定 -- cooldown 未到期的锁定保留
        self._strategy_context.clear_locks(ctx.date)

        # 写入 context 供后续步骤使用
        ctx.slice_ = slice_
        ctx.account_view = account_view

        return StepResult.ok()
