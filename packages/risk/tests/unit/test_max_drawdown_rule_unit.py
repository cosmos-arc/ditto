"""MaxDrawdownRule 单元测试。"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.cash import CashBook
from ditto_risk.drawdown.rules import MaxDrawdownRule
from ditto_risk.errors import RiskConfigurationError
from ditto_risk.post_trade import RiskActionType, RiskSeverity


def _account_view(nav: float = 100_000.0) -> AccountView:
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=MagicMock(),
    )


def _slice() -> SimpleNamespace:
    return SimpleNamespace(bars={})


class TestMaxDrawdownRule:
    def test_no_drawdown(self) -> None:
        """持续上涨的 NAV 不产生 action。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        actions = rule.scan(_account_view(110_000.0), _slice())
        assert actions == []

    def test_warning_threshold(self) -> None:
        """回撤达到 warning 阈值时产生 ALERT。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        actions = rule.scan(_account_view(89_000.0), _slice())
        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT
        assert actions[0].severity == RiskSeverity.WARNING
        assert actions[0].scope == RiskScope.PORTFOLIO
        assert actions[0].instrument_id is None

    def test_emergency_threshold(self) -> None:
        """回撤达到 emergency 阈值时产生 LIQUIDATE。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        actions = rule.scan(_account_view(75_000.0), _slice())
        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.LIQUIDATE
        assert actions[0].severity == RiskSeverity.EMERGENCY

    def test_reset_clears_peak(self) -> None:
        """reset 清除 peak NAV，从新起点计算回撤。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        rule.reset()
        # peak is now 0, so 90000 should not trigger
        actions = rule.scan(_account_view(90_000.0), _slice())
        assert actions == []

    def test_peak_updates_only_on_new_high(self) -> None:
        """peak 仅在新高时更新。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        # NAV drops to 95k, peak stays at 100k
        rule.scan(_account_view(95_000.0), _slice())
        # NAV drops to 89k, drawdown = (100k-89k)/100k = 11% > 10%
        actions = rule.scan(_account_view(89_000.0), _slice())
        assert len(actions) == 1
        assert actions[0].severity == RiskSeverity.WARNING

    def test_zero_nav_returns_empty(self) -> None:
        """NAV = 0 时返回空列表。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        actions = rule.scan(_account_view(0.0), _slice())
        assert actions == []

    def test_invalid_thresholds_rejected(self) -> None:
        """warning >= emergency 时抛 RiskConfigurationError。"""
        with pytest.raises(RiskConfigurationError, match="warning_threshold"):
            MaxDrawdownRule(warning_threshold=0.20, emergency_threshold=0.10)

    def test_negative_threshold_rejected(self) -> None:
        """负阈值时抛 RiskConfigurationError。"""
        with pytest.raises(RiskConfigurationError, match="non-negative"):
            MaxDrawdownRule(warning_threshold=-0.1, emergency_threshold=0.2)
