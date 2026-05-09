"""DrawdownStateSnapshot / MaxDrawdownRule 快照恢复单元测试。"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock

from ditto_portfolio.accounting import AccountView, CashBook
from ditto_risk.drawdown.rules import DrawdownStateSnapshot, MaxDrawdownRule
from ditto_risk.post_trade import RiskAction


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


class TestDrawdownStateSnapshot:
    def test_snapshot_captures_peak_nav(self) -> None:
        """扫描至峰值后，snapshot 捕获 peak_nav。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        rule.scan(_account_view(120_000.0), _slice())
        snap = rule.snapshot()
        assert snap.peak_nav == 120_000.0

    def test_snapshot_from_initial_state(self) -> None:
        """未扫描时，snapshot 的 peak_nav == 0.0。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        snap = rule.snapshot()
        assert snap.peak_nav == 0.0

    def test_restore_resets_peak_nav(self) -> None:
        """restore 恢复内部 peak_nav 到快照值。"""
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        rule.scan(_account_view(100_000.0), _slice())
        rule.scan(_account_view(120_000.0), _slice())
        snap = rule.snapshot()

        rule.reset()
        assert rule._peak_nav == 0.0

        rule.restore(snap)
        assert rule._peak_nav == 120_000.0

    def test_snapshot_is_frozen(self) -> None:
        """DrawdownStateSnapshot 是不可变的。"""
        snap = DrawdownStateSnapshot(peak_nav=100.0)
        mutated = False
        try:
            snap.peak_nav = 200.0  # type: ignore[misc]
        except AttributeError:
            mutated = True
        assert mutated, "frozen dataclass 不允许属性赋值"

    def test_replay_after_restore_produces_same_actions(self) -> None:
        """快照恢复后继续扫描，与完整重放产生一致的 actions。"""
        nav_series_first = [100_000.0, 120_000.0, 95_000.0]
        nav_series_second = [100_000.0, 80_000.0]
        nav_series_full = nav_series_first + nav_series_second

        # --- 路径 A: 扫描 → 快照 → 重置 → 恢复 → 继续扫描 ---
        rule_a = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        actions_a_first: list[RiskAction] = []
        for nav in nav_series_first:
            actions_a_first.extend(rule_a.scan(_account_view(nav), _slice()))

        snap = rule_a.snapshot()
        rule_a.reset()
        rule_a.restore(snap)

        actions_a_second: list[RiskAction] = []
        for nav in nav_series_second:
            actions_a_second.extend(rule_a.scan(_account_view(nav), _slice()))

        actions_a = actions_a_first + actions_a_second

        # --- 路径 B: 完整重放 ---
        rule_b = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        actions_b: list[RiskAction] = []
        for nav in nav_series_full:
            actions_b.extend(rule_b.scan(_account_view(nav), _slice()))

        # 断言：两条路径产生相同数量和类型的 actions
        assert len(actions_a) == len(actions_b)
        for a, b in zip(actions_a, actions_b, strict=True):
            assert a.action_type == b.action_type
            assert a.severity == b.severity
            assert a.current_value == b.current_value
