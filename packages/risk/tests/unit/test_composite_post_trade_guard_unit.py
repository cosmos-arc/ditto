"""CompositePostTradeGuard 单元测试。"""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting import AccountView, CashBook
from ditto_risk.post_trade import (
    CompositePostTradeGuard,
    RiskAction,
    RiskActionType,
    RiskSeverity,
)

IID = InstrumentId(1)


def _account_view(nav: float = 100_000.0) -> AccountView:
    return AccountView(
        positions=MappingProxyType({}),
        cash=CashBook(available=nav, settled=nav, frozen=0.0),
        total_value=nav,
        nav=nav,
        exposure=0.0,
    )


def _slice() -> MagicMock:
    return MagicMock(bars={})


class _StubRule:
    """可控行为的 stub rule。"""

    def __init__(self, actions: list[RiskAction] | None = None) -> None:
        self._actions = actions or []
        self.reset_called = False

    def scan(self, account_view: AccountView, slice_: object) -> list[RiskAction]:
        return list(self._actions)

    def reset(self) -> None:
        self.reset_called = True


def _make_action(rule_id: str = "stub") -> RiskAction:
    return RiskAction(
        action_type=RiskActionType.ALERT,
        instrument_id=IID,
        scope=RiskScope.INSTRUMENT,
        severity=RiskSeverity.WARNING,
        rule_id=rule_id,
        detail="test",
        current_value=0.1,
        threshold=0.05,
    )


class TestCompositePostTradeGuard:
    def test_no_actions(self) -> None:
        """所有规则无触发时返回空列表。"""
        guard = CompositePostTradeGuard(
            rules=(_StubRule(actions=[]), _StubRule(actions=[])),
        )
        actions = guard.scan(_account_view(), _slice())
        assert actions == []

    def test_collects_all_actions(self) -> None:
        """合并所有规则的 actions。"""
        action_a = _make_action(rule_id="rule_a")
        action_b = _make_action(rule_id="rule_b")
        guard = CompositePostTradeGuard(
            rules=(_StubRule(actions=[action_a]), _StubRule(actions=[action_b])),
        )
        actions = guard.scan(_account_view(), _slice())
        assert len(actions) == 2
        assert actions[0].rule_id == "rule_a"
        assert actions[1].rule_id == "rule_b"

    def test_fires_callbacks(self) -> None:
        """扫描完成后回调被调用。"""
        action = _make_action()
        callback = MagicMock()
        guard = CompositePostTradeGuard(
            rules=(_StubRule(actions=[action]),),
            callbacks=(callback,),
        )
        guard.scan(_account_view(), _slice())
        callback.assert_called_once_with([action])

    def test_reset_resets_all(self) -> None:
        """reset 传播到所有子规则。"""
        rule_a = _StubRule()
        rule_b = _StubRule()
        guard = CompositePostTradeGuard(rules=(rule_a, rule_b))
        guard.reset()
        assert rule_a.reset_called
        assert rule_b.reset_called

    def test_multiple_callbacks(self) -> None:
        """多个回调都被调用。"""
        action = _make_action()
        cb1 = MagicMock()
        cb2 = MagicMock()
        guard = CompositePostTradeGuard(
            rules=(_StubRule(actions=[action]),),
            callbacks=(cb1, cb2),
        )
        guard.scan(_account_view(), _slice())
        cb1.assert_called_once()
        cb2.assert_called_once()
