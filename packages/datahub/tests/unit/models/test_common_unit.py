"""Tests for DataHub common models."""

import pytest
from ditto_core.quality.severity import DQSeverity
from ditto_datahub.models import Dataset, Domain
from ditto_datahub.models.common import InstrumentIdRange, OnDuplicate


@pytest.mark.unit
class TestDataset:
    """测试 Dataset 枚举."""

    def test_dataset_values(self) -> None:
        """验证所有数据集枚举值正确."""
        assert Dataset.CALENDAR.value == "calendar"
        assert Dataset.ETF_BASIC.value == "etf_basic"
        assert Dataset.ETF_DAILY.value == "etf_daily"
        assert Dataset.STOCK_BASIC.value == "stock_basic"
        assert Dataset.STOCK_DAILY.value == "stock_daily"
        assert Dataset.STOCK_STATUS.value == "stock_status"
        assert Dataset.ADJ_FACTOR.value == "adj_factor"
        assert Dataset.FUND_ADJ.value == "fund_adj"
        assert Dataset.BALANCE_SHEET.value == "balance_sheet"
        assert Dataset.INCOME_STATEMENT.value == "income_statement"
        assert Dataset.CASH_FLOW.value == "cash_flow"
        assert Dataset.DIVIDEND.value == "dividend"
        assert Dataset.VALUATION_METRICS.value == "valuation_metrics"
        assert Dataset.MARGIN_TRADING.value == "margin_trading"
        assert Dataset.PLEDGE_RATIO.value == "pledge_ratio"
        assert Dataset.MACRO_INDICATORS.value == "macro_indicators"

    def test_index_basic_exists(self) -> None:
        """验证 INDEX_BASIC 枚举存在且值正确."""
        assert hasattr(Dataset, "INDEX_BASIC")
        assert Dataset.INDEX_BASIC.value == "index_basic"

    def test_index_daily_exists(self) -> None:
        """验证 INDEX_DAILY 枚举存在且值正确."""
        assert hasattr(Dataset, "INDEX_DAILY")
        assert Dataset.INDEX_DAILY.value == "index_daily"

    def test_is_basic_dataset(self) -> None:
        """测试 is_basic_dataset 方法."""
        assert Dataset.is_basic_dataset("stock_basic") is True
        assert Dataset.is_basic_dataset("etf_basic") is True
        assert Dataset.is_basic_dataset("index_basic") is True
        assert Dataset.is_basic_dataset("stock_daily") is False
        assert Dataset.is_basic_dataset("stock_status") is False
        assert Dataset.is_basic_dataset("etf_daily") is False
        assert Dataset.is_basic_dataset("index_daily") is False
        assert Dataset.is_basic_dataset("calendar") is False
        assert Dataset.is_basic_dataset("adj_factor") is False
        assert Dataset.is_basic_dataset("fund_adj") is False
        assert Dataset.is_basic_dataset("balance_sheet") is False
        assert Dataset.is_basic_dataset("valuation_metrics") is False

    def test_is_calendar_dataset(self) -> None:
        """测试 is_calendar_dataset 方法."""
        assert Dataset.is_calendar_dataset("calendar") is True
        assert Dataset.is_calendar_dataset("stock_basic") is False
        assert Dataset.is_calendar_dataset("stock_daily") is False

    def test_dataset_is_string_enum(self) -> None:
        """验证 Dataset 是字符串枚举(可以与字符串比较)."""
        assert Dataset.CALENDAR == "calendar"
        assert Dataset.STOCK_DAILY == "stock_daily"
        # [REVIEW] match/case
        match "etf_daily":
            case Dataset.ETF_DAILY:
                assert Dataset.ETF_DAILY.value == "etf_daily"
            case _:
                pytest.fail("应该匹配到 ETF_DAILY")


@pytest.mark.unit
class TestDomain:
    """测试 Domain 枚举."""

    def test_domain_values(self) -> None:
        """验证所有域枚举值正确."""
        assert Domain.METADATA.value == "metadata"
        assert Domain.MARKET.value == "market"
        assert Domain.CAPITAL.value == "capital"
        assert Domain.FUNDAMENTAL.value == "fundamental"
        assert Domain.MACRO.value == "macro"

    def test_domain_is_string_enum(self) -> None:
        """验证 Domain 是字符串枚举."""
        assert Domain.METADATA == "metadata"
        assert Domain.FUNDAMENTAL == "fundamental"

    def test_should_have_five_members(self) -> None:
        """应该有五个成员（五域架构）."""
        assert len(Domain) == 5


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestInstrumentIdRange:
    """测试 InstrumentIdRange NamedTuple."""

    def test_should_create_id_range(self) -> None:
        """应该能够创建 ID 范围."""
        id_range = InstrumentIdRange(min_id=1_000_000, max_id=1_999_999)
        assert id_range.min_id == 1_000_000
        assert id_range.max_id == 1_999_999

    def test_should_get_stock_range(self) -> None:
        """应该能够获取股票 ID 范围."""
        stock_range = InstrumentIdRange.get_range("stock")
        assert stock_range.min_id == 1_000_000
        assert stock_range.max_id == 1_999_999

    def test_should_get_etf_range(self) -> None:
        """应该能够获取 ETF ID 范围."""
        etf_range = InstrumentIdRange.get_range("etf")
        assert etf_range.min_id == 2_000_000
        assert etf_range.max_id == 2_999_999

    def test_should_get_index_range(self) -> None:
        """应该能够获取指数 ID 范围."""
        index_range = InstrumentIdRange.get_range("index")
        assert index_range.min_id == 3_000_000
        assert index_range.max_id == 3_999_999

    def test_should_raise_error_for_unknown_asset_class(self) -> None:
        """未知的资产类别应该抛出异常."""
        with pytest.raises(ValueError, match="Unknown asset class"):
            InstrumentIdRange.get_range("unknown")

    def test_detect_stock_asset_class(self) -> None:
        """应该能够检测股票资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([1_000_001, 1_500_000])
        assert asset_class == "stock"

    def test_detect_etf_asset_class(self) -> None:
        """应该能够检测 ETF 资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([2_000_001, 2_500_000])
        assert asset_class == "etf"

    def test_detect_index_asset_class(self) -> None:
        """应该能够检测指数资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([3_000_001, 3_500_000])
        assert asset_class == "index"

    def test_detect_boundary_ids(self) -> None:
        """应该能够正确识别边界 ID 值."""
        # Stock boundaries
        assert InstrumentIdRange.detect_asset_class([1_000_000]) == "stock"
        assert InstrumentIdRange.detect_asset_class([1_999_999]) == "stock"
        # ETF boundaries
        assert InstrumentIdRange.detect_asset_class([2_000_000]) == "etf"
        assert InstrumentIdRange.detect_asset_class([2_999_999]) == "etf"
        # Index boundaries
        assert InstrumentIdRange.detect_asset_class([3_000_000]) == "index"
        assert InstrumentIdRange.detect_asset_class([3_999_999]) == "index"

    def test_detect_mixed_asset_classes_raises_error(self) -> None:
        """混合资产类别应该抛出 ValueError."""
        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            InstrumentIdRange.detect_asset_class([1_000_001, 2_000_001])

    def test_detect_empty_id_list_raises_error(self) -> None:
        """空 ID 列表应该抛出 ValueError（严格模式）."""
        with pytest.raises(ValueError, match="无法推断空"):
            InstrumentIdRange.detect_asset_class([])

    def test_detect_unrecognized_ids_raises_error(self) -> None:
        """无法识别的 ID 应该抛出 ValueError（严格模式）."""
        with pytest.raises(ValueError, match="不在任何已定义范围内"):
            InstrumentIdRange.detect_asset_class([9_999_999])

    # ============ 新增资产类别测试 ============

    def test_should_get_fx_range(self) -> None:
        """应该能够获取外汇 ID 范围."""
        fx_range = InstrumentIdRange.get_range("fx")
        assert fx_range.min_id == 4_000_000
        assert fx_range.max_id == 4_999_999

    def test_should_get_commodity_range(self) -> None:
        """应该能够获取大宗商品 ID 范围."""
        commodity_range = InstrumentIdRange.get_range("commodity")
        assert commodity_range.min_id == 5_000_000
        assert commodity_range.max_id == 5_999_999

    def test_should_get_bond_range(self) -> None:
        """应该能够获取债券 ID 范围."""
        bond_range = InstrumentIdRange.get_range("bond")
        assert bond_range.min_id == 6_000_000
        assert bond_range.max_id == 6_999_999

    def test_should_get_futures_range(self) -> None:
        """应该能够获取期货 ID 范围."""
        futures_range = InstrumentIdRange.get_range("futures")
        assert futures_range.min_id == 7_000_000
        assert futures_range.max_id == 7_999_999

    def test_should_get_option_range(self) -> None:
        """应该能够获取期权 ID 范围."""
        option_range = InstrumentIdRange.get_range("option")
        assert option_range.min_id == 8_000_000
        assert option_range.max_id == 8_999_999

    def test_detect_fx_asset_class(self) -> None:
        """应该能够检测外汇资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([4_000_001, 4_500_000])
        assert asset_class == "fx"

    def test_detect_commodity_asset_class(self) -> None:
        """应该能够检测大宗商品资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([5_000_001, 5_500_000])
        assert asset_class == "commodity"

    def test_detect_bond_asset_class(self) -> None:
        """应该能够检测债券资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([6_000_001, 6_500_000])
        assert asset_class == "bond"

    def test_detect_futures_asset_class(self) -> None:
        """应该能够检测期货资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([7_000_001, 7_500_000])
        assert asset_class == "futures"

    def test_detect_option_asset_class(self) -> None:
        """应该能够检测期权资产类别."""
        asset_class = InstrumentIdRange.detect_asset_class([8_000_001, 8_500_000])
        assert asset_class == "option"

    def test_detect_new_asset_class_boundaries(self) -> None:
        """应该能够正确识别新增资产类别的边界 ID 值."""
        # FX boundaries
        assert InstrumentIdRange.detect_asset_class([4_000_000]) == "fx"
        assert InstrumentIdRange.detect_asset_class([4_999_999]) == "fx"
        # Commodity boundaries
        assert InstrumentIdRange.detect_asset_class([5_000_000]) == "commodity"
        assert InstrumentIdRange.detect_asset_class([5_999_999]) == "commodity"
        # Bond boundaries
        assert InstrumentIdRange.detect_asset_class([6_000_000]) == "bond"
        assert InstrumentIdRange.detect_asset_class([6_999_999]) == "bond"
        # Futures boundaries
        assert InstrumentIdRange.detect_asset_class([7_000_000]) == "futures"
        assert InstrumentIdRange.detect_asset_class([7_999_999]) == "futures"
        # Option boundaries
        assert InstrumentIdRange.detect_asset_class([8_000_000]) == "option"
        assert InstrumentIdRange.detect_asset_class([8_999_999]) == "option"
