"""
DataFetchStep 单元测试.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

from ditto_backtest.data_feed import Slice
from ditto_backtest.steps import DataFetchStep, StepContext, TradingStep
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext

from ._helpers import (
    IID_1,
    IID_2,
    _make_account_view,
    _make_clock,
    _make_slice,
    _make_snapshot,
)


class TestDataFetchStep:
    """DataFetchStep: 获取 Slice + 账户快照 + 清除锁定。"""

    def test_sets_slice_and_account_view(self) -> None:
        """执行后 ctx.slice_ 和 ctx.account_view 被正确设置。"""
        slice_ = _make_slice(bars={IID_1: _make_snapshot(IID_1)})
        account_view = _make_account_view()
        clock = _make_clock()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=clock,
            brokerage=Mock(get_account=Mock(return_value=account_view)),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.slice_ is slice_
        assert ctx.account_view is account_view

    def test_advances_clock(self) -> None:
        """执行后 clock.advance_to 被调用。"""
        step_time = datetime(2026, 3, 1, 15, 0)
        slice_ = Slice(
            trade_date="2026-03-01",
            step_time=step_time,
            bars={IID_1: _make_snapshot(IID_1)},
        )
        clock = _make_clock()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=clock,
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        clock.advance_to.assert_called_once_with(step_time)

    def test_collects_input_instruments(self) -> None:
        """slice_.bars 的所有 instrument_id 被收集到 input_instruments。"""
        bars = {
            IID_1: _make_snapshot(IID_1),
            IID_2: _make_snapshot(IID_2),
        }
        slice_ = _make_slice(bars=bars)
        input_instruments: set[InstrumentId] = set()

        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=input_instruments,
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        assert IID_1 in input_instruments
        assert IID_2 in input_instruments

    def test_clears_strategy_context_locks(self) -> None:
        """执行后 strategy_context 的到期锁被清除。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-02-28"（已过期），date = "2026-03-01"
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-02-28")

        slice_ = _make_slice()
        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        # 锁在 2026-02-28 到期，2026-03-01 清除
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        # cooldown_until < date -> 锁被清除
        assert not strategy_context.is_locked(IID_1)

    def test_preserves_active_strategy_context_locks(self) -> None:
        """未到期锁在 clear_locks 后仍然保留。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-03-05"（未过期）
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-03-05")

        slice_ = _make_slice()
        step = DataFetchStep(
            data_feed=Mock(get_slice=Mock(return_value=slice_)),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        step.execute(ctx)

        # cooldown_until > date -> 锁保留
        assert strategy_context.is_locked(IID_1)

    def test_satisfies_trading_step_protocol(self) -> None:
        """DataFetchStep 满足 TradingStep Protocol。"""
        step: TradingStep = DataFetchStep(  # type: ignore[assignment]
            data_feed=Mock(get_slice=Mock(return_value=_make_slice())),
            clock=_make_clock(),
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        result = step.execute(ctx)
        assert result.success is True
