"""SingleLossLimitRule 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting import AccountView, CashBook, Position
from ditto_risk.drawdown.rules import SingleLossLimitRule
from ditto_risk.errors import RiskConfigurationError
from ditto_risk.post_trade import RiskActionType, RiskSeverity

IID = InstrumentId(1)


def _pos(average_cost: float = 100.0) -> Position:
    return Position(
        instrument_id=IID,
        quantity=1000,
        available_quantity=1000,
        average_cost=average_cost,
        market_value=average_cost * 1000,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _account_view(positions: dict[InstrumentId, Position] | None = None) -> AccountView:
    return AccountView(
        positions=MappingProxyType(positions or {}),
        cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
        total_value=100_000.0,
        nav=100_000.0,
        exposure=50_000.0,
    )


class _Bar:
    def __init__(self, close: float, prev_close: float = 100.0) -> None:
        self.close = close
        self.prev_close = prev_close


def _slice(bars: dict[InstrumentId, _Bar] | None = None) -> MagicMock:
    return MagicMock(bars=bars or {})


class TestSingleLossLimitRule:
    def test_no_loss(self) -> None:
        """价格未跌破阈值时不产生 action。"""
        rule = SingleLossLimitRule(threshold=0.15)
        # average_cost=100, threshold=15%, loss_limit=85, close=90 > 85
        bars = {IID: _Bar(close=90.0)}
        actions = rule.scan(
            _account_view({IID: _pos(average_cost=100.0)}), _slice(bars)
        )
        assert actions == []

    def test_loss_below_threshold(self) -> None:
        """价格跌破阈值时产生 REDUCE_POSITION。"""
        rule = SingleLossLimitRule(threshold=0.15)
        # average_cost=100, threshold=15%, loss_limit=85, close=80 < 85
        bars = {IID: _Bar(close=80.0)}
        actions = rule.scan(
            _account_view({IID: _pos(average_cost=100.0)}), _slice(bars)
        )
        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.REDUCE_POSITION
        assert actions[0].instrument_id == IID
        assert actions[0].scope == RiskScope.INSTRUMENT
        assert actions[0].severity == RiskSeverity.CRITICAL
        assert actions[0].rule_id == "single_loss_limit"

    def test_no_bar_data_skipped(self) -> None:
        """无行情数据时跳过。"""
        rule = SingleLossLimitRule(threshold=0.15)
        actions = rule.scan(
            _account_view({IID: _pos(average_cost=100.0)}),
            _slice({}),
        )
        assert actions == []

    def test_threshold_zero_rejected(self) -> None:
        """阈值 <= 0 时抛 RiskConfigurationError。"""
        with pytest.raises(RiskConfigurationError, match="positive"):
            SingleLossLimitRule(threshold=0.0)

    def test_reset_is_noop(self) -> None:
        """reset 不报错。"""
        rule = SingleLossLimitRule(threshold=0.15)
        rule.reset()  # should not raise
