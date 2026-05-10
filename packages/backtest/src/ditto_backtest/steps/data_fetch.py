"""
DataFetchStep -- 账户快照 + 清除到期锁定 + 数据指纹累积.

Synchronizer 提供的 bars 已通过 StepContext.bars 传入，
本步骤仅负责：
  1. brokerage.get_account() -> AccountView
  2. input_instruments.update(bars.keys())
  3. bar_fingerprints 累积 (date, close) 用于数据指纹
  4. strategy_context.clear_locks(date)
"""

from __future__ import annotations

from ditto_execution.brokerage import Brokerage
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext

from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["DataFetchStep"]


class DataFetchStep:
    """
    数据获取步骤 -- 账户快照 + 数据指纹 + 清除到期锁定.

    bars 数据由 Synchronizer 通过 StepContext.bars 提供。
    执行后 ctx.account_view 被设置。
    """

    def __init__(
        self,
        brokerage: Brokerage,
        strategy_context: StrategyContext,
        input_instruments: set[InstrumentId],
        bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
    ) -> None:
        self._brokerage = brokerage
        self._strategy_context = strategy_context
        self._input_instruments = input_instruments
        self._bar_fingerprints = bar_fingerprints

    def execute(self, ctx: StepContext) -> StepResult:
        """获取账户快照并累积数据指纹。"""
        account_view = self._brokerage.get_account()
        trade_date = ctx.time_context.trade_date

        # 收集输入标的 -- 用于 RunManifest input_refs
        self._input_instruments.update(ctx.bars.keys())

        # 累积 bar 数据指纹 -- (date, close) per instrument
        for iid, bar in ctx.bars.items():
            if iid not in self._bar_fingerprints:
                self._bar_fingerprints[iid] = []
            self._bar_fingerprints[iid].append((trade_date, bar.close))

        # 每日清除到期锁定 -- cooldown 未到期的锁定保留
        self._strategy_context.clear_locks(trade_date)

        # 写入 context 供后续步骤使用
        ctx.account_view = account_view

        return StepResult.ok()
