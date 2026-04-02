"""
DataLateArrivalPolicy 和 LateArrivalChecker 单元测试.

测试数据延迟到达策略枚举、检查结果模型和检查函数。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from ditto_data.models.ingestion import (
    DataLateArrivalPolicy,
    LateArrivalCheckResult,
    LateArrivalRejectedError,
)
from ditto_data.services.late_arrival import check_late_arrival


class TestDataLateArrivalPolicy:
    """测试 DataLateArrivalPolicy 枚举."""

    def test_enum_values(self) -> None:
        """枚举值应包含 REJECT、ACCEPT、REBUILD."""
        assert DataLateArrivalPolicy.REJECT == "reject"
        assert DataLateArrivalPolicy.ACCEPT == "accept"
        assert DataLateArrivalPolicy.REBUILD == "rebuild"

    def test_enum_members_count(self) -> None:
        """枚举应有且仅有 3 个成员."""
        assert len(DataLateArrivalPolicy) == 3


class TestLateArrivalCheckResult:
    """测试 LateArrivalCheckResult 数据类."""

    def test_accepted_result(self) -> None:
        """接受的检查结果."""
        result = LateArrivalCheckResult(
            accepted=True,
            needs_rebuild=False,
            delay_days=0,
            policy=DataLateArrivalPolicy.ACCEPT,
        )
        assert result.accepted is True
        assert result.needs_rebuild is False
        assert result.delay_days == 0

    def test_rebuild_result(self) -> None:
        """需要重建的检查结果."""
        result = LateArrivalCheckResult(
            accepted=True,
            needs_rebuild=True,
            delay_days=10,
            policy=DataLateArrivalPolicy.REBUILD,
        )
        assert result.accepted is True
        assert result.needs_rebuild is True
        assert result.delay_days == 10


class TestCheckLateArrivalAccept:
    """测试 ACCEPT 策略 — 始终接受."""

    @pytest.mark.parametrize(
        ("trade_date", "knowledge_date"),
        [
            (date(2024, 1, 1), date(2024, 1, 1)),  # 同日
            (date(2024, 1, 1), date(2024, 1, 2)),  # 延迟 1 天
            (date(2024, 1, 1), date(2024, 12, 31)),  # 延迟很大
        ],
    )
    def test_accept_alows_all(
        self,
        trade_date: date,
        knowledge_date: date,
    ) -> None:
        """ACCEPT 策略不应拒绝任何数据."""
        result = check_late_arrival(
            knowledge_date=knowledge_date,
            trade_date=trade_date,
            policy=DataLateArrivalPolicy.ACCEPT,
        )

        assert result.accepted is True
        assert result.needs_rebuild is False


class TestCheckLateArrivalReject:
    """测试 REJECT 策略 — 超过阈值拒绝."""

    def test_reject_within_threshold(self) -> None:
        """延迟天数 <= max_delay_days 时接受."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 6),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REJECT,
            max_delay_days=5,
        )
        assert result.accepted is True
        assert result.needs_rebuild is False
        assert result.delay_days == 5

    def test_reject_at_exact_threshold(self) -> None:
        """延迟天数 == max_delay_days 时接受（边界条件）."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 6),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REJECT,
            max_delay_days=5,
        )
        assert result.accepted is True
        assert result.delay_days == 5

    def test_reject_exceeds_threshold(self) -> None:
        """延迟天数 > max_delay_days 时拒绝."""
        with pytest.raises(LateArrivalRejectedError) as exc_info:
            check_late_arrival(
                knowledge_date=date(2024, 1, 7),
                trade_date=date(2024, 1, 1),
                policy=DataLateArrivalPolicy.REJECT,
                max_delay_days=5,
            )

        assert exc_info.value.delay_days == 6
        assert exc_info.value.max_delay_days == 5

    def test_reject_same_day(self) -> None:
        """knowledge_date == trade_date 时延迟为 0，应接受."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 1),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REJECT,
            max_delay_days=0,
        )
        assert result.accepted is True
        assert result.delay_days == 0

    def test_reject_zero_threshold_one_day_late(self) -> None:
        """max_delay_days=0 时，延迟 1 天即拒绝."""
        with pytest.raises(LateArrivalRejectedError) as exc_info:
            check_late_arrival(
                knowledge_date=date(2024, 1, 2),
                trade_date=date(2024, 1, 1),
                policy=DataLateArrivalPolicy.REJECT,
                max_delay_days=0,
            )

        assert exc_info.value.delay_days == 1
        assert exc_info.value.max_delay_days == 0

    def test_reject_negative_delay_impossible(self) -> None:
        """knowledge_date < trade_date 时延迟为 0（不会出现负值）."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 1),
            trade_date=date(2024, 1, 5),
            policy=DataLateArrivalPolicy.REJECT,
            max_delay_days=0,
        )
        # knowledge_date 在 trade_date 之前，意味着数据提前已知
        assert result.accepted is True
        assert result.delay_days == 0


class TestCheckLateArrivalRebuild:
    """测试 REBUILD 策略 — 接受但标记需重建."""

    def test_rebuild_no_delay(self) -> None:
        """无延迟时不需要重建."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 1),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REBUILD,
            max_delay_days=0,
        )
        assert result.accepted is True
        assert result.needs_rebuild is False
        assert result.delay_days == 0

    def test_rebuild_within_threshold(self) -> None:
        """延迟在阈值内但大于 0 时需要重建."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 3),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REBUILD,
            max_delay_days=5,
        )
        assert result.accepted is True
        assert result.needs_rebuild is True
        assert result.delay_days == 2

    def test_rebuild_exceeds_threshold_still_accepted(self) -> None:
        """延迟超过阈值时仍然接受，但需要重建."""
        result = check_late_arrival(
            knowledge_date=date(2024, 1, 10),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REBUILD,
            max_delay_days=5,
        )
        assert result.accepted is True
        assert result.needs_rebuild is True
        assert result.delay_days == 9


class TestCheckLateArrivalDefaultMaxDelay:
    """测试默认 max_delay_days 参数."""

    def test_default_max_delay_is_infinite(self) -> None:
        """不传 max_delay_days 时，REJECT 策略使用默认值（非常大的数）."""
        # 即使延迟 1000 天也不应被拒绝
        knowledge = date(2024, 1, 1) + timedelta(days=1000)
        result = check_late_arrival(
            knowledge_date=knowledge,
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REJECT,
        )
        assert result.accepted is True


class TestLateArrivalRejectedError:
    """测试 LateArrivalRejectedError 异常."""

    def test_error_attributes(self) -> None:
        """异常应包含 delay_days 和 max_delay_days 属性."""
        error = LateArrivalRejectedError(
            delay_days=10,
            max_delay_days=5,
            trade_date="2024-01-01",
            knowledge_date="2024-01-11",
        )
        assert error.delay_days == 10
        assert error.max_delay_days == 5
        assert error.trade_date == "2024-01-01"
        assert error.knowledge_date == "2024-01-11"

    def test_error_message(self) -> None:
        """错误消息应包含关键信息."""
        error = LateArrivalRejectedError(
            delay_days=10,
            max_delay_days=5,
            trade_date="2024-01-01",
            knowledge_date="2024-01-11",
        )
        message = str(error)
        assert "10" in message
        assert "5" in message
        assert "2024-01-01" in message
