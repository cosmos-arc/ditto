"""Kill Switch 类型单元测试 — 三级熔断机制."""

from __future__ import annotations

import pytest
from ditto_risk.kill_switch import KillSwitchDecision, KillSwitchLevel

# ---------------------------------------------------------------------------
# KillSwitchLevel enum
# ---------------------------------------------------------------------------


def test_kill_switch_level_has_exactly_three_members() -> None:
    """KillSwitchLevel 应包含恰好三个成员."""
    assert len(KillSwitchLevel) == 3


def test_kill_switch_level_member_names() -> None:
    """KillSwitchLevel 成员名为 ALERT_ONLY / HALT_NEW_ORDERS / LIQUIDATE_ALL."""
    names = {m.name for m in KillSwitchLevel}
    assert names == {"ALERT_ONLY", "HALT_NEW_ORDERS", "LIQUIDATE_ALL"}


def test_kill_switch_level_alert_only_value() -> None:
    """ALERT_ONLY 的值为 'alert_only'."""
    assert KillSwitchLevel.ALERT_ONLY == "alert_only"


def test_kill_switch_level_halt_new_orders_value() -> None:
    """HALT_NEW_ORDERS 的值为 'halt_new_orders'."""
    assert KillSwitchLevel.HALT_NEW_ORDERS == "halt_new_orders"


def test_kill_switch_level_liquidate_all_value() -> None:
    """LIQUIDATE_ALL 的值为 'liquidate_all'."""
    assert KillSwitchLevel.LIQUIDATE_ALL == "liquidate_all"


def test_kill_switch_level_is_str_enum() -> None:
    """KillSwitchLevel 是 StrEnum，成员 isinstance str."""
    assert isinstance(KillSwitchLevel.ALERT_ONLY, str)
    assert isinstance(KillSwitchLevel.HALT_NEW_ORDERS, str)
    assert isinstance(KillSwitchLevel.LIQUIDATE_ALL, str)


def test_kill_switch_level_liquidate_is_most_severe() -> None:
    """LIQUIDATE_ALL 应为最严重的级别（按枚举定义顺序排在最后）."""
    members = list(KillSwitchLevel)
    assert members[-1] == KillSwitchLevel.LIQUIDATE_ALL


# ---------------------------------------------------------------------------
# KillSwitchDecision dataclass
# ---------------------------------------------------------------------------


def test_decision_construction_with_all_fields() -> None:
    """KillSwitchDecision 应支持全字段构造."""
    decision = KillSwitchDecision(
        level=KillSwitchLevel.HALT_NEW_ORDERS,
        reason="drawdown exceeded 15%",
        triggered_at="2024-01-15T09:30:00",
        order_ids=("ORD-001", "ORD-002"),
    )
    assert decision.level == KillSwitchLevel.HALT_NEW_ORDERS
    assert decision.reason == "drawdown exceeded 15%"
    assert decision.triggered_at == "2024-01-15T09:30:00"
    assert decision.order_ids == ("ORD-001", "ORD-002")


def test_decision_default_order_ids_is_empty_tuple() -> None:
    """KillSwitchDecision 默认 order_ids 为空元组."""
    decision = KillSwitchDecision(
        level=KillSwitchLevel.ALERT_ONLY,
        reason="volatility spike",
        triggered_at="2024-01-15T10:00:00",
    )
    assert decision.order_ids == ()


def test_decision_is_frozen() -> None:
    """KillSwitchDecision 应为 frozen（不可变）."""
    decision = KillSwitchDecision(
        level=KillSwitchLevel.ALERT_ONLY,
        reason="test",
        triggered_at="2024-01-15T10:00:00",
    )
    with pytest.raises(AttributeError):
        decision.reason = "mutated"  # type: ignore[misc]


def test_decision_level_isinstance_kill_switch_level() -> None:
    """decision.level 应通过 isinstance 检查 KillSwitchLevel."""
    decision = KillSwitchDecision(
        level=KillSwitchLevel.LIQUIDATE_ALL,
        reason="emergency halt",
        triggered_at="2024-01-15T14:00:00",
    )
    assert isinstance(decision.level, KillSwitchLevel)


def test_decision_order_ids_is_tuple() -> None:
    """order_ids 字段类型为 tuple，不接受列表."""
    decision = KillSwitchDecision(
        level=KillSwitchLevel.LIQUIDATE_ALL,
        reason="emergency",
        triggered_at="2024-01-15T14:00:00",
        order_ids=("ORD-001",),
    )
    assert isinstance(decision.order_ids, tuple)
    assert decision.order_ids == ("ORD-001",)
