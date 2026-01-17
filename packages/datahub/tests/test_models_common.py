"""测试 models/common.py 中的枚举类和 NamedTuple."""

import pytest
from ditto_datahub.models.common import AssetSidRange, DQSeverity, OnDuplicate


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


class TestAssetSidRange:
    """测试 AssetSidRange NamedTuple."""

    def test_should_create_sid_range(self) -> None:
        """应该能够创建 SID 范围."""
        sid_range = AssetSidRange(min_sid=1_000_000, max_sid=1_999_999)
        assert sid_range.min_sid == 1_000_000
        assert sid_range.max_sid == 1_999_999

    def test_should_get_stock_range(self) -> None:
        """应该能够获取股票 SID 范围."""
        stock_range = AssetSidRange.get_range("stock")
        assert stock_range.min_sid == 1_000_000
        assert stock_range.max_sid == 1_999_999

    def test_should_get_etf_range(self) -> None:
        """应该能够获取 ETF SID 范围."""
        etf_range = AssetSidRange.get_range("etf")
        assert etf_range.min_sid == 2_000_000
        assert etf_range.max_sid == 2_999_999

    def test_should_get_index_range(self) -> None:
        """应该能够获取指数 SID 范围."""
        index_range = AssetSidRange.get_range("index")
        assert index_range.min_sid == 3_000_000
        assert index_range.max_sid == 3_999_999

    def test_should_raise_error_for_unknown_asset_class(self) -> None:
        """未知的资产类别应该抛出异常."""
        with pytest.raises(ValueError, match="Unknown asset class"):
            AssetSidRange.get_range("unknown")

    def test_detect_stock_asset_class(self) -> None:
        """应该能够检测股票资产类别."""
        asset_class = AssetSidRange.detect_asset_class([1_000_001, 1_500_000])
        assert asset_class == "stock"

    def test_detect_etf_asset_class(self) -> None:
        """应该能够检测 ETF 资产类别."""
        asset_class = AssetSidRange.detect_asset_class([2_000_001, 2_500_000])
        assert asset_class == "etf"

    def test_detect_index_asset_class(self) -> None:
        """应该能够检测指数资产类别."""
        asset_class = AssetSidRange.detect_asset_class([3_000_001, 3_500_000])
        assert asset_class == "index"

    def test_detect_boundary_sids(self) -> None:
        """应该能够正确识别边界 SID 值."""
        # Stock boundaries
        assert AssetSidRange.detect_asset_class([1_000_000]) == "stock"
        assert AssetSidRange.detect_asset_class([1_999_999]) == "stock"
        # ETF boundaries
        assert AssetSidRange.detect_asset_class([2_000_000]) == "etf"
        assert AssetSidRange.detect_asset_class([2_999_999]) == "etf"
        # Index boundaries
        assert AssetSidRange.detect_asset_class([3_000_000]) == "index"
        assert AssetSidRange.detect_asset_class([3_999_999]) == "index"

    def test_detect_mixed_asset_classes_raises_error(self) -> None:
        """混合资产类别应该抛出 ValueError."""
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            AssetSidRange.detect_asset_class([1_000_001, 2_000_001])

    def test_detect_empty_sid_list_defaults_to_stock(self) -> None:
        """空 SID 列表应该返回默认值 'stock'."""
        asset_class = AssetSidRange.detect_asset_class([])
        assert asset_class == "stock"

    def test_detect_unrecognized_sids_defaults_to_stock(self) -> None:
        """无法识别的 SID 应该返回默认值 'stock'."""
        # SID outside all ranges
        asset_class = AssetSidRange.detect_asset_class([9_999_999])
        assert asset_class == "stock"
