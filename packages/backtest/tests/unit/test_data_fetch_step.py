"""
DataFetchStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.steps import DataFetchStep, TradingStep
from ditto_execution.orders.book import OrderBookReadOnly
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext
from packages.backtest.tests.unit._helpers import (
    IID_1,
    IID_2,
    _make_account_view,
    _make_ctx,
    _make_snapshot,
)


class TestDataFetchStep:
    """DataFetchStep: 获取 Slice + 账户快照 + 清除锁定。"""

    def test_sets_account_view(self) -> None:
        """执行后 ctx.account_view 被正确设置。"""
        account_view = _make_account_view()
        bars = {IID_1: _make_snapshot(IID_1)}

        step = DataFetchStep(
            brokerage=Mock(get_account=Mock(return_value=account_view)),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = _make_ctx(bars=bars)
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.account_view is account_view

    def test_collects_input_instruments(self) -> None:
        """ctx.bars 的所有 instrument_id 被收集到 input_instruments。"""
        bars = {
            IID_1: _make_snapshot(IID_1),
            IID_2: _make_snapshot(IID_2),
        }
        input_instruments: set[InstrumentId] = set()

        step = DataFetchStep(
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=input_instruments,
            bar_fingerprints={},
        )

        ctx = _make_ctx(bars=bars)
        step.execute(ctx)

        assert IID_1 in input_instruments
        assert IID_2 in input_instruments

    def test_clears_strategy_context_locks(self) -> None:
        """执行后 strategy_context 的到期锁被清除。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-02-28"（已过期），date = "2026-03-01"
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-02-28")

        step = DataFetchStep(
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        # 锁在 2026-02-28 到期，2026-03-01 清除
        ctx = _make_ctx()
        step.execute(ctx)

        # cooldown_until < date -> 锁被清除
        assert not strategy_context.is_locked(IID_1)

    def test_preserves_active_strategy_context_locks(self) -> None:
        """未到期锁在 clear_locks 后仍然保留。"""
        strategy_context = StrategyContext()
        # cooldown_until = "2026-03-05"（未过期）
        strategy_context.lock_instrument(IID_1, "risk", cooldown_until="2026-03-05")

        step = DataFetchStep(
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=strategy_context,
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = _make_ctx()
        step.execute(ctx)

        # cooldown_until > date -> 锁保留
        assert strategy_context.is_locked(IID_1)

    def test_sets_order_book(self) -> None:
        """执行后 ctx.order_book 被设置为 OrderBookReadOnly。"""
        account_view = _make_account_view()
        order_book_view = OrderBookReadOnly({})
        bars = {IID_1: _make_snapshot(IID_1)}

        step = DataFetchStep(
            brokerage=Mock(
                get_account=Mock(return_value=account_view),
                get_order_book=Mock(return_value=order_book_view),
            ),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )

        ctx = _make_ctx(bars=bars)
        result = step.execute(ctx)

        assert result.success is True
        assert ctx.order_book is order_book_view

    def test_satisfies_trading_step_protocol(self) -> None:
        """DataFetchStep 满足 TradingStep Protocol。"""
        step: TradingStep = DataFetchStep(  # type: ignore[assignment]
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            strategy_context=StrategyContext(),
            input_instruments=set(),
            bar_fingerprints={},
        )
        ctx = _make_ctx()
        result = step.execute(ctx)
        assert result.success is True
