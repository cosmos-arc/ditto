"""Tests for _coordinator_constants — 共享常量 + 指数工具函数."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app.process._coordinator_constants import (
    MARKET_INDEX_CODES,
    STYLE_INDEX_CODES,
    SUPPORTED_INSTRUMENT_DATASETS,
    get_all_index_codes,
    get_default_index_codes,
    get_sw_index_codes,
)
from ditto_data.models import Dataset

# ---------------------------------------------------------------------------
# SUPPORTED_INSTRUMENT_DATASETS
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSupportedInstrumentDatasets:
    """测试 SUPPORTED_INSTRUMENT_DATASETS 与 Dataset 枚举的一致性."""

    def test_all_members_are_valid_dataset_values(self) -> None:
        """集合中每个成员都是有效的 Dataset 枚举值."""
        valid_values = set(Dataset)
        for member in SUPPORTED_INSTRUMENT_DATASETS:
            assert member in valid_values, f"{member!r} 不在 Dataset 枚举中"

    def test_is_frozen_set(self) -> None:
        """SUPPORTED_INSTRUMENT_DATASETS 是 set 类型."""
        assert isinstance(SUPPORTED_INSTRUMENT_DATASETS, set)

    def test_contains_expected_datasets(self) -> None:
        """包含关键预期数据集."""
        expected = {
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.STOCK_STATUS,
        }
        assert expected.issubset(SUPPORTED_INSTRUMENT_DATASETS)

    def test_does_not_contain_non_instrument_datasets(self) -> None:
        """不应包含非按标的摄取的数据集（如 calendar、stock_basic）."""
        non_instrument = {Dataset.CALENDAR, Dataset.STOCK_BASIC, Dataset.ETF_BASIC}
        assert SUPPORTED_INSTRUMENT_DATASETS.isdisjoint(non_instrument)


# ---------------------------------------------------------------------------
# get_sw_index_codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSwIndexCodes:
    """测试 get_sw_index_codes 从 SWIndustryProvider 获取申万行业指数."""

    @pytest.fixture
    def mock_source(self) -> MagicMock:
        """创建满足 SWIndustryProvider 协议的 mock."""
        source = MagicMock()
        source.fetch_sw_industry.return_value = pl.DataFrame(
            {
                "source_ticker": ["801010.SI", "801020.SI", "801030.SI"],
                "industry_name": ["农林牧渔", "采掘", "化工"],
            }
        )
        return source

    def test_returns_sorted_unique_codes(self, mock_source: MagicMock) -> None:
        """返回排序后的唯一 source_ticker 列表."""
        result = get_sw_index_codes(mock_source, level=1)

        assert result == ["801010.SI", "801020.SI", "801030.SI"]
        mock_source.fetch_sw_industry.assert_called_once_with(level=1)

    def test_deduplicates_codes(self, mock_source: MagicMock) -> None:
        """重复的 source_ticker 应去重."""
        mock_source.fetch_sw_industry.return_value = pl.DataFrame(
            {
                "source_ticker": ["801010.SI", "801010.SI", "801020.SI"],
                "industry_name": ["农林牧渔", "农林牧渔", "采掘"],
            }
        )

        result = get_sw_index_codes(mock_source, level=1)
        assert result == ["801010.SI", "801020.SI"]

    def test_empty_dataframe_returns_empty_list(self, mock_source: MagicMock) -> None:
        """数据源返回空 DataFrame 时返回空列表."""
        mock_source.fetch_sw_industry.return_value = pl.DataFrame(
            {"source_ticker": [], "industry_name": []}
        )

        result = get_sw_index_codes(mock_source, level=1)
        assert result == []

    def test_level_2_passed_through(self, mock_source: MagicMock) -> None:
        """level=2 正确传递到 fetch_sw_industry."""
        get_sw_index_codes(mock_source, level=2)

        mock_source.fetch_sw_industry.assert_called_once_with(level=2)


# ---------------------------------------------------------------------------
# get_default_index_codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDefaultIndexCodes:
    """测试 get_default_index_codes 固定配置指数列表."""

    def test_include_style_true(self) -> None:
        """include_style=True 返回市场指数 + 风格指数."""
        result = get_default_index_codes(include_style=True)

        # 验证包含所有市场指数
        for code in MARKET_INDEX_CODES:
            assert code in result

        # 验证包含所有风格指数
        for code in STYLE_INDEX_CODES:
            assert code in result

    def test_include_style_false(self) -> None:
        """include_style=False 仅返回市场指数，不含风格指数."""
        result = get_default_index_codes(include_style=False)

        # 验证包含所有市场指数
        for code in MARKET_INDEX_CODES:
            assert code in result

        # 验证不包含任何风格指数
        for code in STYLE_INDEX_CODES:
            assert code not in result

    def test_default_parameter_includes_style(self) -> None:
        """默认参数 include_style=True."""
        result = get_default_index_codes()

        for code in STYLE_INDEX_CODES:
            assert code in result

    def test_returns_list_type(self) -> None:
        """返回类型为 list."""
        result = get_default_index_codes()
        assert isinstance(result, list)

    def test_market_indices_come_before_style(self) -> None:
        """市场指数排在风格指数之前."""
        result = get_default_index_codes(include_style=True)

        last_market_idx = len(MARKET_INDEX_CODES) - 1
        first_style_idx = len(MARKET_INDEX_CODES)

        assert result[last_market_idx] == MARKET_INDEX_CODES[-1]
        assert result[first_style_idx] == STYLE_INDEX_CODES[0]


# ---------------------------------------------------------------------------
# get_all_index_codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAllIndexCodes:
    """测试 get_all_index_codes 聚合所有指数代码."""

    @pytest.fixture
    def mock_source(self) -> MagicMock:
        """创建满足 SWIndustryProvider 协议的 mock."""
        source = MagicMock()
        source.fetch_sw_industry.return_value = pl.DataFrame(
            {
                "source_ticker": ["801010.SI", "801020.SI"],
                "industry_name": ["农林牧渔", "采掘"],
            }
        )
        return source

    def test_without_sw_levels(self, mock_source: MagicMock) -> None:
        """include_sw_levels=None 时不追加 SW 行业指数."""
        result = get_all_index_codes(
            source=mock_source, include_style=True, include_sw_levels=None
        )

        assert result == get_default_index_codes(include_style=True)
        mock_source.fetch_sw_industry.assert_not_called()

    def test_with_sw_level_1(self, mock_source: MagicMock) -> None:
        """include_sw_levels=[1] 时追加 SW 一级行业指数."""
        result = get_all_index_codes(
            source=mock_source, include_style=True, include_sw_levels=[1]
        )

        # 市场指数 + 风格指数 + SW 指数
        expected_len = len(MARKET_INDEX_CODES) + len(STYLE_INDEX_CODES) + 2
        assert len(result) == expected_len
        assert "801010.SI" in result
        assert "801020.SI" in result

    def test_with_sw_levels_1_and_2(self, mock_source: MagicMock) -> None:
        """include_sw_levels=[1, 2] 时追加两级 SW 行业指数."""
        result = get_all_index_codes(
            source=mock_source, include_style=True, include_sw_levels=[1, 2]
        )

        # 每次 fetch 返回 2 条，调用两次
        expected_len = len(MARKET_INDEX_CODES) + len(STYLE_INDEX_CODES) + 4
        assert len(result) == expected_len
        assert mock_source.fetch_sw_industry.call_count == 2

    def test_without_style_with_sw(self, mock_source: MagicMock) -> None:
        """include_style=False 且 include_sw_levels=[1] 时不包含风格指数但包含 SW."""
        result = get_all_index_codes(
            source=mock_source, include_style=False, include_sw_levels=[1]
        )

        # 不含风格指数
        for code in STYLE_INDEX_CODES:
            assert code not in result

        # 含 SW 指数
        assert "801010.SI" in result

    def test_empty_sw_result_appends_nothing(self, mock_source: MagicMock) -> None:
        """SW 数据源返回空时，结果仅包含固定指数."""
        mock_source.fetch_sw_industry.return_value = pl.DataFrame(
            {"source_ticker": [], "industry_name": []}
        )

        result = get_all_index_codes(
            source=mock_source, include_style=True, include_sw_levels=[1]
        )

        assert result == get_default_index_codes(include_style=True)
