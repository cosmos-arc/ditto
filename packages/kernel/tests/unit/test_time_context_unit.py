"""ditto_kernel.time_context 单元测试."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time

import pytest
from ditto_kernel.time_context import TimeContext


class TestTimeContextConstruction:
    """TimeContext 构造测试."""

    def test_basic_construction(self) -> None:
        """应正确构造 TimeContext."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        assert tc.decision_time == datetime(2024, 6, 15, 15, 0)
        assert tc.knowledge_date == date(2024, 6, 14)
        assert tc.trade_date == "2024-06-15"

    def test_fields_are_accessible(self) -> None:
        """所有字段应可通过属性访问."""
        tc = TimeContext(
            decision_time=datetime(2024, 1, 1),
            knowledge_date=date(2024, 1, 1),
            trade_date="2024-01-01",
        )
        assert tc.decision_time is not None
        assert tc.knowledge_date is not None
        assert tc.trade_date is not None


class TestTimeContextFrozen:
    """TimeContext frozen 语义测试."""

    def test_frozen_prevents_attribute_assignment(self) -> None:
        """frozen dataclass 不允许修改属性."""
        tc = TimeContext(
            decision_time=datetime(2024, 1, 1),
            knowledge_date=date(2024, 1, 1),
            trade_date="2024-01-01",
        )
        with pytest.raises(FrozenInstanceError):
            tc.trade_date = "2024-12-31"  # type: ignore[misc]

    def test_frozen_prevents_decision_time_assignment(self) -> None:
        """frozen dataclass 不允许修改 decision_time."""
        tc = TimeContext(
            decision_time=datetime(2024, 1, 1),
            knowledge_date=date(2024, 1, 1),
            trade_date="2024-01-01",
        )
        with pytest.raises(FrozenInstanceError):
            tc.decision_time = datetime(2025, 1, 1)  # type: ignore[misc]


class TestPitCutoff:
    """pit_cutoff 属性测试."""

    def test_pit_cutoff_returns_datetime_at_midnight(self) -> None:
        """pit_cutoff 应返回 knowledge_date 当天零点的 datetime."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        assert tc.pit_cutoff == datetime(2024, 6, 14, 0, 0, 0)

    def test_pit_cutoff_is_combine_knowledge_date_time_min(self) -> None:
        """pit_cutoff 应等于 datetime.combine(knowledge_date, time.min)."""
        knowledge = date(2024, 3, 20)
        tc = TimeContext(
            decision_time=datetime(2024, 3, 21, 9, 30),
            knowledge_date=knowledge,
            trade_date="2024-03-21",
        )
        assert tc.pit_cutoff == datetime.combine(knowledge, time.min)

    def test_pit_cutoff_with_t_plus_1_semantics(self) -> None:
        """T+1 语义下，knowledge_date = trade_date - 1 天."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        assert tc.pit_cutoff == datetime(2024, 6, 14, 0, 0)
        # knowledge_date 在 trade_date 之前（T+1）
        assert tc.knowledge_date < tc.decision_time.date()


class TestTimeContextEquality:
    """TimeContext 值相等性测试."""

    def test_equal_instances_are_equal(self) -> None:
        """相同字段值的 TimeContext 应相等."""
        tc1 = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        tc2 = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        assert tc1 == tc2

    def test_different_trade_date_not_equal(self) -> None:
        """不同 trade_date 的 TimeContext 不应相等."""
        tc1 = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        tc2 = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-16",
        )
        assert tc1 != tc2

    def test_hashable(self) -> None:
        """frozen dataclass 应可用作 dict key / set 元素."""
        tc = TimeContext(
            decision_time=datetime(2024, 6, 15, 15, 0),
            knowledge_date=date(2024, 6, 14),
            trade_date="2024-06-15",
        )
        assert hash(tc) == hash(tc)
        assert len({tc, tc}) == 1
