"""Tests for DataHub common models."""

import pytest
from ditto_datahub.models import Dataset


@pytest.mark.unit
class TestDataset:
    """测试 Dataset 枚举。"""

    def test_dataset_values(self) -> None:
        """验证所有数据集枚举值正确。"""
        assert Dataset.CALENDAR.value == "calendar"
        assert Dataset.ETF_BASIC.value == "etf_basic"
        assert Dataset.ETF_DAILY.value == "etf_daily"
        assert Dataset.STOCK_BASIC.value == "stock_basic"
        assert Dataset.STOCK_DAILY.value == "stock_daily"
        assert Dataset.ADJ_FACTOR.value == "adj_factor"
        assert Dataset.FUND_ADJ.value == "fund_adj"

    def test_is_basic_dataset(self) -> None:
        """测试 is_basic_dataset 方法。"""
        assert Dataset.is_basic_dataset("stock_basic") is True
        assert Dataset.is_basic_dataset("etf_basic") is True
        assert Dataset.is_basic_dataset("stock_daily") is False
        assert Dataset.is_basic_dataset("etf_daily") is False
        assert Dataset.is_basic_dataset("calendar") is False
        assert Dataset.is_basic_dataset("adj_factor") is False
        assert Dataset.is_basic_dataset("fund_adj") is False

    def test_is_calendar_dataset(self) -> None:
        """测试 is_calendar_dataset 方法。"""
        assert Dataset.is_calendar_dataset("calendar") is True
        assert Dataset.is_calendar_dataset("stock_basic") is False
        assert Dataset.is_calendar_dataset("stock_daily") is False

    def test_dataset_is_string_enum(self) -> None:
        """验证 Dataset 是字符串枚举（可以与字符串比较）。"""
        assert Dataset.CALENDAR == "calendar"
        assert Dataset.STOCK_DAILY == "stock_daily"
        # 可以用于 match/case
        match "etf_daily":
            case Dataset.ETF_DAILY:
                assert True
            case _:
                pytest.fail("应该匹配到 ETF_DAILY")
