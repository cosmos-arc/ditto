"""Market SourceSchema 单元测试

测试 Market 域 SourceSchema 的定义和验证功能。
"""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.errors import SchemaValidationError
from ditto_datahub.sources.schemas import (
    ADJ_FACTOR_SOURCE_SCHEMA,
    ETF_DAILY_SOURCE_SCHEMA,
    FUND_ADJ_SOURCE_SCHEMA,
    STOCK_DAILY_SOURCE_SCHEMA,
    STOCK_LIMIT_SOURCE_SCHEMA,
    STOCK_STATUS_SOURCE_SCHEMA,
)


class TestStockDailySourceSchema:
    """测试 STOCK_DAILY_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "open": [10.0, 20.0],
                "high": [10.5, 20.5],
                "low": [9.5, 19.5],
                "close": [10.2, 20.2],
                "pre_close": [10.0, 20.0],
                "volume": [1000000.0, 2000000.0],
                "amount": [10000000.0, 20000000.0],
                "pct_change": [2.0, 1.0],
            }
        )

        # 应该通过验证
        STOCK_DAILY_SOURCE_SCHEMA.validate(df)

    def test_validate_missing_columns(self) -> None:
        """测试缺少列的情况"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 1, 2)],
                # 缺少 open, high, low 等列
            }
        )

        # 应该抛出异常
        with pytest.raises(SchemaValidationError) as exc_info:
            STOCK_DAILY_SOURCE_SCHEMA.validate(df)

        assert "Missing columns" in str(exc_info.value)

    def test_validate_duplicate_keys(self) -> None:
        """测试重复主键的情况"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000001.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "open": [10.0, 10.5],
                "high": [10.5, 11.0],
                "low": [9.5, 10.0],
                "close": [10.2, 10.7],
                "pre_close": [10.0, 10.0],
                "volume": [1000000.0, 1100000.0],
                "amount": [10000000.0, 11000000.0],
                "pct_change": [2.0, 2.5],
            }
        )

        # 应该抛出异常
        with pytest.raises(SchemaValidationError) as exc_info:
            STOCK_DAILY_SOURCE_SCHEMA.validate(df)

        assert "Duplicate keys" in str(exc_info.value)


class TestAdjFactorSourceSchema:
    """测试 ADJ_FACTOR_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "knowledge_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "adj_factor": [1.2345, 1.1234],
            }
        )

        # 应该通过验证
        ADJ_FACTOR_SOURCE_SCHEMA.validate(df)

    def test_validate_missing_knowledge_date(self) -> None:
        """测试缺少 knowledge_date 列"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ"],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [1.2345],
            }
        )

        # 应该抛出异常
        with pytest.raises(SchemaValidationError) as exc_info:
            ADJ_FACTOR_SOURCE_SCHEMA.validate(df)

        assert "Missing columns" in str(exc_info.value)


class TestStockStatusSourceSchema:
    """测试 STOCK_STATUS_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000001.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "is_suspended": [False, True],
                "suspend_timing": ["", "停牌"],
                "is_st": [False, True],
                "st_type": ["", "ST"],
                "list_status": ["L", "L"],
            }
        )

        # 应该通过验证（允许重复主键）
        STOCK_STATUS_SOURCE_SCHEMA.validate(df)

    def test_validate_duplicate_keys_allowed(self) -> None:
        """测试允许重复主键"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000001.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "is_suspended": [False, True],
                "suspend_timing": ["", "停牌"],
                "is_st": [False, True],
                "st_type": ["", "ST"],
                "list_status": ["L", "L"],
            }
        )

        # 应该通过验证（空主键，不验证唯一性）
        STOCK_STATUS_SOURCE_SCHEMA.validate(df)


class TestEtfDailySourceSchema:
    """测试 ETF_DAILY_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["510300.SH", "510500.SH"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "open": [4.5, 5.5],
                "high": [4.6, 5.6],
                "low": [4.4, 5.4],
                "close": [4.55, 5.55],
                "pre_close": [4.5, 5.5],
                "volume": [1000000.0, 2000000.0],
                "amount": [4550000.0, 11100000.0],
                "pct_change": [1.11, 0.91],
            }
        )

        # 应该通过验证
        ETF_DAILY_SOURCE_SCHEMA.validate(df)


class TestStockLimitSourceSchema:
    """测试 STOCK_LIMIT_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "up_limit": [11.0, 22.0],
                "down_limit": [9.0, 18.0],
            }
        )

        # 应该通过验证
        STOCK_LIMIT_SOURCE_SCHEMA.validate(df)


class TestFundAdjSourceSchema:
    """测试 FUND_ADJ_SOURCE_SCHEMA"""

    def test_validate_valid_data(self) -> None:
        """测试验证有效数据"""
        df = pl.DataFrame(
            {
                "src_code": ["000001.OF", "000002.OF"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "knowledge_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "adj_factor": [1.1, 1.2],
            }
        )

        # 应该通过验证
        FUND_ADJ_SOURCE_SCHEMA.validate(df)
