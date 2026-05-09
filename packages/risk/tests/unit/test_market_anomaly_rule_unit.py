"""MarketAnomalyRule 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

import pytest
from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting import AccountView, CashBook
from ditto_risk.errors import RiskConfigurationError
from ditto_risk.exposure.rules import MarketAnomalyRule
from ditto_risk.post_trade import RiskActionType, RiskSeverity

IID = InstrumentId(1)


def _account_view() -> AccountView:
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=50_000.0, settled=50_000.0, frozen=0.0),
        total_value=100_000.0,
        nav=100_000.0,
        exposure=0.0,
        pending_buy_value=0.0,
        order_book=MagicMock(),
    )


class _Bar:
    def __init__(self, close: float, prev_close: float = 100.0) -> None:
        self.close = close
        self.prev_close = prev_close


def _slice(bars: dict[InstrumentId, _Bar]) -> MagicMock:
    return MagicMock(bars=bars)


class TestMarketAnomalyRule:
    def test_no_anomaly(self) -> None:
        """正常波动不产生 action。"""
        rule = MarketAnomalyRule(threshold=0.05)
        # daily_return = |103/100 - 1| = 3% < 5%
        bars = {IID: _Bar(close=103.0, prev_close=100.0)}
        actions = rule.scan(_account_view(), _slice(bars))
        assert actions == []

    def test_anomaly_detected(self) -> None:
        """异常波动产生 ALERT。"""
        rule = MarketAnomalyRule(threshold=0.05)
        # daily_return = |108/100 - 1| = 8% > 5%
        bars = {IID: _Bar(close=108.0, prev_close=100.0)}
        actions = rule.scan(_account_view(), _slice(bars))
        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT
        assert actions[0].instrument_id == IID
        assert actions[0].scope == RiskScope.INSTRUMENT
        assert actions[0].severity == RiskSeverity.WARNING
        assert actions[0].rule_id == "market_anomaly"

    def test_anomaly_negative_direction(self) -> None:
        """下跌方向同样检测异常。"""
        rule = MarketAnomalyRule(threshold=0.05)
        # daily_return = |90/100 - 1| = 10% > 5%
        bars = {IID: _Bar(close=90.0, prev_close=100.0)}
        actions = rule.scan(_account_view(), _slice(bars))
        assert len(actions) == 1

    def test_zero_prev_close_skipped(self) -> None:
        """prev_close <= 0 时跳过。"""
        rule = MarketAnomalyRule(threshold=0.05)
        bars = {IID: _Bar(close=108.0, prev_close=0.0)}
        actions = rule.scan(_account_view(), _slice(bars))
        assert actions == []

    def test_threshold_zero_rejected(self) -> None:
        """阈值 <= 0 时抛 RiskConfigurationError。"""
        with pytest.raises(RiskConfigurationError, match="positive"):
            MarketAnomalyRule(threshold=0.0)
