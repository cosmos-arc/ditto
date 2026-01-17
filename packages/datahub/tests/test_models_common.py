"""测试 models/common.py 中的枚举类和 NamedTuple."""

import pytest
from ditto_datahub.models.common import DQSeverity, OnDuplicate, SidRange


class TestDQSeverity:
    """测试 DQSeverity 枚举."""

    def test_should_have_three_severity_levels(self) -> None:
        """应该有三个严重程度级别."""
        assert DQSeverity.ERROR.value == "error"
        assert DQSeverity.WARNING.value == "warning"
        assert DQSeverity.ALERT.value == "alert"

    def test_should_be_string_enum(self) -> None:
        """应该是字符串枚举."""
        assert isinstance(DQSeverity.ERROR.value, str)

    def test_should_have_three_members(self) -> None:
        """应该有三个成员."""
        assert len(DQSeverity) == 3


class TestOnDuplicate:
    """测试 OnDuplicate 枚举."""

    def test_should_have_three_strategies(self) -> None:
        """应该有三种重复处理策略."""
        assert OnDuplicate.ERROR.value == "error"
        assert OnDuplicate.KEEP_FIRST.value == "keep_first"
        assert OnDuplicate.KEEP_LAST.value == "keep_last"

    def test_should_have_three_members(self) -> None:
        """应该有三个成员."""
        assert len(OnDuplicate) == 3


class TestSidRange:
    """测试 SidRange NamedTuple."""

    def test_should_create_sid_range(self) -> None:
        """应该能够创建 SID 范围."""
        sid_range = SidRange(min_sid=1_000_000, max_sid=1_999_999)
        assert sid_range.min_sid == 1_000_000
        assert sid_range.max_sid == 1_999_999

    def test_should_get_stock_range(self) -> None:
        """应该能够获取股票 SID 范围."""
        stock_range = SidRange.get_range("stock")
        assert stock_range.min_sid == 1_000_000
        assert stock_range.max_sid == 1_999_999

    def test_should_get_etf_range(self) -> None:
        """应该能够获取 ETF SID 范围."""
        etf_range = SidRange.get_range("etf")
        assert etf_range.min_sid == 2_000_000
        assert etf_range.max_sid == 2_999_999

    def test_should_get_index_range(self) -> None:
        """应该能够获取指数 SID 范围."""
        index_range = SidRange.get_range("index")
        assert index_range.min_sid == 3_000_000
        assert index_range.max_sid == 3_999_999

    def test_should_raise_error_for_unknown_asset_class(self) -> None:
        """未知的资产类别应该抛出异常."""
        with pytest.raises(ValueError, match="Unknown asset class"):
            SidRange.get_range("unknown")
