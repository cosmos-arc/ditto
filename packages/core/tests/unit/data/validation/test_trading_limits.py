"""涨跌停识别测试."""

from datetime import date

import pytest
from ditto_core.data.validation.trading_limits import TradingLimitsChecker


class TestTradingLimitsChecker:
    """涨跌停识别器测试."""

    @pytest.fixture
    def checker(self) -> TradingLimitsChecker:
        """创建涨跌停检查器实例."""
        return TradingLimitsChecker()

    def test_normal_price_not_limit(self, checker: TradingLimitsChecker) -> None:
        """测试正常价格不被识别为涨跌停."""
        # 前收盘价 10.00, 当日价格在 9.00-11.00 之间
        result = checker.check_limit_status(
            symbol="510300",
            close=10.50,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
        )

        assert result.is_limit_up is False
        assert result.is_limit_down is False
        assert result.limit_type == "normal"

    def test_regular_limit_up(self, checker: TradingLimitsChecker) -> None:
        """测试普通涨停(10%)."""
        # 前收盘价 10.00, 涨停价 11.00
        result = checker.check_limit_status(
            symbol="510300",
            close=11.00,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
        )

        assert result.is_limit_up is True
        assert result.is_limit_down is False
        assert result.limit_type == "limit_up"
        assert result.limit_ratio == pytest.approx(0.10, rel=1e-3)

    def test_regular_limit_down(self, checker: TradingLimitsChecker) -> None:
        """测试普通跌停(10%)."""
        # 前收盘价 10.00, 跌停价 9.00
        result = checker.check_limit_status(
            symbol="510300",
            close=9.00,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
        )

        assert result.is_limit_up is False
        assert result.is_limit_down is True
        assert result.limit_type == "limit_down"
        assert result.limit_ratio == pytest.approx(-0.10, rel=1e-3)

    def test_st_limit_up(self, checker: TradingLimitsChecker) -> None:
        """测试ST股票涨停(5%)."""
        # 前收盘价 10.00, ST涨停价 10.50
        result = checker.check_limit_status(
            symbol="ST001",
            close=10.50,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=True,
        )

        assert result.is_limit_up is True
        assert result.is_limit_down is False
        assert result.limit_type == "st_limit_up"
        assert result.limit_ratio == pytest.approx(0.05, rel=1e-3)

    def test_st_limit_down(self, checker: TradingLimitsChecker) -> None:
        """测试ST股票跌停(5%)."""
        # 前收盘价 10.00, ST跌停价 9.50
        result = checker.check_limit_status(
            symbol="ST001",
            close=9.50,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=True,
        )

        assert result.is_limit_up is False
        assert result.is_limit_down is True
        assert result.limit_type == "st_limit_down"
        assert result.limit_ratio == pytest.approx(-0.05, rel=1e-3)

    def test_ipo_first_day_limit_up(self, checker: TradingLimitsChecker) -> None:
        """测试新股首日涨停限制(20%)."""
        # 新股首日无前收盘价, 使用发行价
        result = checker.check_limit_status(
            symbol="N001",
            close=24.00,
            prev_close=20.00,  # 发行价
            date=date(2024, 12, 11),
            is_st=False,
            is_ipo_first_day=True,
        )

        assert result.is_limit_up is True
        assert result.is_limit_down is False
        assert result.limit_type == "ipo_limit_up"
        assert result.limit_ratio == pytest.approx(0.20, rel=1e-3)

    def test_science_tech_limit_up(self, checker: TradingLimitsChecker) -> None:
        """测试科创板/创业板涨停(20%)."""
        # 科创板股票前两日无涨跌幅限制, 之后为20%
        result = checker.check_limit_status(
            symbol="688001",  # 科创板代码
            close=12.00,
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
            board_type="star",  # 科创板
        )

        assert result.is_limit_up is True
        assert result.is_limit_down is False
        assert result.limit_type == "sci_tech_limit_up"
        assert result.limit_ratio == pytest.approx(0.20, rel=1e-3)

    def test_suspended_trading(self, checker: TradingLimitsChecker) -> None:
        """测试停牌状态."""
        result = checker.check_limit_status(
            symbol="510300",
            close=None,  # 停牌无价格
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
            is_suspended=True,
        )

        assert result.is_limit_up is False
        assert result.is_limit_down is False
        assert result.limit_type == "suspended"
        assert result.is_suspended is True

    def test_rounding_errors(self, checker: TradingLimitsChecker) -> None:
        """测试四舍五入导致的边界情况."""
        # 价格精度到2位小数
        result = checker.check_limit_status(
            symbol="510300",
            close=11.005,  # 理论涨停价 11.00
            prev_close=10.00,
            date=date(2024, 12, 11),
            is_st=False,
        )

        # 考虑到价格精度, 这应该被视为涨停
        assert result.is_limit_up is True
        assert result.limit_type == "limit_up"

    def test_missing_previous_close(self, checker: TradingLimitsChecker) -> None:
        """测试缺少前收盘价的情况."""
        # 首次上市或数据缺失
        result = checker.check_limit_status(
            symbol="510300",
            close=10.00,
            prev_close=None,
            date=date(2024, 12, 11),
            is_st=False,
        )

        assert result.limit_type == "no_previous_close"
        assert result.is_limit_up is False
        assert result.is_limit_down is False

    def test_batch_check(self, checker: TradingLimitsChecker) -> None:
        """测试批量检查."""
        data = [
            {"symbol": "510300", "close": 11.00, "prev_close": 10.00, "is_st": False},
            {"symbol": "ST001", "close": 9.50, "prev_close": 10.00, "is_st": True},
            {
                "symbol": "688001",
                "close": 12.00,
                "prev_close": 10.00,
                "is_st": False,
                "board_type": "star",
            },
        ]

        results = checker.batch_check(data, date=date(2024, 12, 11))

        assert len(results) == 3
        assert results[0].limit_type == "limit_up"
        assert results[1].limit_type == "st_limit_down"
        assert results[2].limit_type == "sci_tech_limit_up"
