"""ConcentrationLimitRule 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.cash import CashBook
from ditto_portfolio.accounting.position import Position
from ditto_risk.exposure.rules import ConcentrationLimitRule
from ditto_risk.post_trade import RiskActionType, RiskSeverity

IID = InstrumentId(1)


def _pos(market_value: float = 10_000.0) -> Position:
    return Position(
        instrument_id=IID,
        quantity=1000,
        available_quantity=1000,
        average_cost=10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _account_view(
    nav: float = 100_000.0,
    positions: dict[InstrumentId, Position] | None = None,
) -> AccountView:
    return AccountView(
        positions=MappingProxyType(positions or {}),
        cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
        total_value=100_000.0,
        nav=nav,
        exposure=50_000.0,
        pending_buy_value=0.0,
        order_book=MagicMock(),
    )


def _slice() -> MagicMock:
    return MagicMock(bars={})


class TestConcentrationLimitRule:
    def test_within_limit(self) -> None:
        """权重在限额内不产生 action。"""
        rule = ConcentrationLimitRule(max_weight=0.20)
        # nav=100000, market_value=10000, weight=10% < 20%
        actions = rule.scan(
            _account_view(nav=100_000.0, positions={IID: _pos(market_value=10_000.0)}),
            _slice(),
        )
        assert actions == []

    def test_over_limit(self) -> None:
        """权重超限时产生 REDUCE_POSITION。"""
        rule = ConcentrationLimitRule(max_weight=0.20)
        # nav=100000, market_value=30000, weight=30% > 20%
        actions = rule.scan(
            _account_view(nav=100_000.0, positions={IID: _pos(market_value=30_000.0)}),
            _slice(),
        )
        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.REDUCE_POSITION
        assert actions[0].instrument_id == IID
        assert actions[0].scope == RiskScope.INSTRUMENT
        assert actions[0].severity == RiskSeverity.WARNING
        assert actions[0].rule_id == "concentration_limit"

    def test_zero_nav(self) -> None:
        """NAV <= 0 时返回空列表。"""
        rule = ConcentrationLimitRule(max_weight=0.20)
        actions = rule.scan(
            _account_view(nav=0.0, positions={IID: _pos(market_value=30_000.0)}),
            _slice(),
        )
        assert actions == []

    def test_reset_is_noop(self) -> None:
        """reset 不报错。"""
        rule = ConcentrationLimitRule(max_weight=0.20)
        rule.reset()  # should not raise
