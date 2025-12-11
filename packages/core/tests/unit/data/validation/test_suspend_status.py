"""停牌状态处理测试."""

from datetime import date

import pytest
from ditto_core.data.validation.suspend_status import SuspendInfo, SuspendStatusDetector


class TestSuspendStatusDetector:
    """停牌状态检测器测试."""

    @pytest.fixture
    def detector(self) -> SuspendStatusDetector:
        """创建停牌检测器实例."""
        return SuspendStatusDetector()

    def test_detect_continuous_suspension(
        self, detector: SuspendStatusDetector
    ) -> None:
        """测试连续停牌检测."""
        # 连续3天无交易数据, 判断为停牌
        trading_dates = [
            date(2024, 12, 1),
            date(2024, 12, 2),
            date(2024, 12, 3),
            date(2024, 12, 4),
            date(2024, 12, 5),
        ]

        # 只有前两天有数据
        price_data = [
            {"date": date(2024, 12, 1), "volume": 1000000, "close": 10.0},
            {"date": date(2024, 12, 2), "volume": 1500000, "close": 10.5},
            # 后3天无数据
        ]

        suspend_info = detector.detect_suspend_status(
            symbol="510300",
            trading_dates=trading_dates,
            price_data=price_data,
            detection_date=date(2024, 12, 5),
        )

        assert suspend_info.is_suspended is True
        assert suspend_info.suspend_start_date == date(2024, 12, 3)
        assert suspend_info.suspend_days == 3
        assert suspend_info.reason == "no_trading_data"

    def test_detect_trading_resume(self, detector: SuspendStatusDetector) -> None:
        """检测停牌恢复交易."""
        trading_dates = [
            date(2024, 12, 1),
            date(2024, 12, 2),
            date(2024, 12, 3),  # 无数据
            date(2024, 12, 4),  # 无数据
            date(2024, 12, 5),  # 恢复交易
        ]

        price_data = [
            {"date": date(2024, 12, 1), "volume": 1000000, "close": 10.0},
            {"date": date(2024, 12, 2), "volume": 1500000, "close": 10.5},
            {"date": date(2024, 12, 5), "volume": 500000, "close": 10.3},
        ]

        suspend_info = detector.detect_suspend_status(
            symbol="510300",
            trading_dates=trading_dates,
            price_data=price_data,
            detection_date=date(2024, 12, 5),
        )

        assert suspend_info.is_suspended is False
        assert suspend_info.suspend_days == 0
        assert suspend_info.reason == "trading_resumed"

    def test_detect_zero_volume_suspension(
        self, detector: SuspendStatusDetector
    ) -> None:
        """检测成交量为0的停牌."""
        trading_dates = [
            date(2024, 12, 1),
            date(2024, 12, 2),
            date(2024, 12, 3),
        ]

        price_data = [
            {"date": date(2024, 12, 1), "volume": 1000000, "close": 10.0},
            {"date": date(2024, 12, 2), "volume": 0, "close": 10.0},  # 停牌
            {"date": date(2024, 12, 3), "volume": 0, "close": 10.0},  # 停牌
        ]

        suspend_info = detector.detect_suspend_status(
            symbol="510300",
            trading_dates=trading_dates,
            price_data=price_data,
            detection_date=date(2024, 12, 3),
            consecutive_days=2,  # 成交量为0的停牌阈值设为2天
        )

        assert suspend_info.is_suspended is True
        assert suspend_info.suspend_start_date == date(2024, 12, 2)
        assert suspend_info.suspend_days == 2
        assert suspend_info.reason == "zero_volume"

    def test_detect_abnormal_price_suspension(
        self, detector: SuspendStatusDetector
    ) -> None:
        """检测价格异常导致的停牌."""
        trading_dates = [
            date(2024, 12, 1),
            date(2024, 12, 2),
        ]

        price_data = [
            {"date": date(2024, 12, 1), "volume": 1000000, "close": 10.0},
            {"date": date(2024, 12, 2), "volume": 1000000, "close": 5.0},  # 异常跌停
        ]

        suspend_info = detector.detect_suspend_status(
            symbol="510300",
            trading_dates=trading_dates,
            price_data=price_data,
            detection_date=date(2024, 12, 2),
        )

        # 价格跌停不一定停牌, 只是标记为异常
        assert suspend_info.is_suspended is False
        assert suspend_info.is_abnormal_price is True
        assert suspend_info.reason == "abnormal_price_change"

    def test_batch_detect_suspend_status(self, detector: SuspendStatusDetector) -> None:
        """测试批量检测停牌状态."""
        symbols_data = {
            "510300": [
                {"date": date(2024, 12, 1), "volume": 1000000, "close": 10.0},
                # 后续无数据 - 只有2天无数据, 低于默认阈值3
            ],
            "159915": [
                {"date": date(2024, 12, 1), "volume": 1000000, "close": 2.0},
                {"date": date(2024, 12, 2), "volume": 0, "close": 2.0},  # 停牌
                {"date": date(2024, 12, 3), "volume": 500000, "close": 2.1},  # 恢复
            ],
        }

        trading_dates = [
            date(2024, 12, 1),
            date(2024, 12, 2),
            date(2024, 12, 3),
        ]

        results = detector.batch_detect(
            symbols_data=symbols_data,
            trading_dates=trading_dates,
            detection_date=date(2024, 12, 3),
        )

        assert len(results) == 2
        # 510300只有2天无数据, 低于默认阈值3, 不算停牌
        assert results["510300"].is_suspended is False
        assert results["159915"].is_suspended is False

    def test_update_suspend_history(self, detector: SuspendStatusDetector) -> None:
        """测试更新停牌历史记录."""
        # 创建一个模拟的停牌信息
        suspend_info = SuspendInfo(
            symbol="510300",
            is_suspended=True,
            suspend_start_date=date(2024, 12, 2),
            suspend_days=1,
            reason="no_trading_data",
        )

        # 手动更新停牌历史
        detector._update_suspend_history("510300", suspend_info)

        # 检查停牌历史
        history = detector.get_suspend_history("510300")
        assert len(history) == 1
        assert history[0]["start_date"] == date(2024, 12, 2)
        assert history[0]["end_date"] is None  # 仍在停牌

    def test_weekend_holiday_skip(self, detector: SuspendStatusDetector) -> None:
        """测试跳过周末和节假日."""
        trading_dates = [
            date(2024, 12, 2),  # 周一
            date(2024, 12, 3),  # 周二
            date(2024, 12, 4),  # 周三
            date(2024, 12, 5),  # 周四
            date(2024, 12, 6),  # 周五
            date(2024, 12, 9),  # 下周一
        ]

        price_data = [
            {"date": date(2024, 12, 2), "volume": 1000000, "close": 10.0},
            {"date": date(2024, 12, 3), "volume": 0, "close": 10.0},  # 周二成交量为0
            {"date": date(2024, 12, 4), "volume": 0, "close": 10.0},  # 周三成交量为0
            {"date": date(2024, 12, 5), "volume": 0, "close": 10.0},  # 周四成交量为0
            {"date": date(2024, 12, 6), "volume": 0, "close": 10.0},  # 周五成交量为0
            # 周末无数据, 不算停牌
            {"date": date(2024, 12, 9), "volume": 1000000, "close": 10.2},  # 下周一恢复
        ]

        suspend_info = detector.detect_suspend_status(
            symbol="510300",
            trading_dates=trading_dates,
            price_data=price_data,
            detection_date=date(2024, 12, 9),
        )

        # 周二至周五连续4天成交量为0, 应该算停牌
        assert suspend_info.is_suspended is True
        assert suspend_info.suspend_start_date == date(2024, 12, 3)
        assert suspend_info.suspend_days == 4
        assert suspend_info.reason == "zero_volume"
        assert suspend_info.total_suspend_days == 4
