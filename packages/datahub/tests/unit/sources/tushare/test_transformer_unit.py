"""Tests for TushareDataTransformer."""

from datetime import date

import polars as pl
from ditto_datahub.sources.tushare.transformer import (
    DAILY_OHLCV_MAPPING,
    ColumnMapping,
    TushareDataTransformer,
)


class TestColumnMapping:
    """Tests for ColumnMapping dataclass."""

    def test_column_mapping_creation(self) -> None:
        """Test creating a ColumnMapping instance."""
        mapping = ColumnMapping(
            rename={"ts_code": "src_code", "vol": "volume"},
            date_columns={"trade_date": "%Y%m%d"},
            float_columns=["open", "high", "low", "close"],
        )

        assert mapping.rename == {"ts_code": "src_code", "vol": "volume"}
        assert mapping.date_columns == {"trade_date": "%Y%m%d"}
        assert mapping.float_columns == ["open", "high", "low", "close"]
        assert mapping.int_columns == ()

    def test_column_mapping_with_boolean_columns(self) -> None:
        """Test ColumnMapping with boolean_columns field."""
        mapping = ColumnMapping(
            rename={},
            date_columns={},
            float_columns=[],
            boolean_columns=("is_open", "is_trading"),
        )

        assert mapping.boolean_columns == ("is_open", "is_trading")
        # 验证默认值为空元组
        default_mapping = ColumnMapping(rename={}, date_columns={}, float_columns=[])
        assert default_mapping.boolean_columns == ()

    def test_column_mapping_with_computed_columns(self) -> None:
        """Test ColumnMapping with computed_columns field."""
        # 创建包含 computed_columns 的映射配置
        mapping = ColumnMapping(
            rename={"ts_code": "src_code"},
            date_columns={},
            float_columns=[],
            computed_columns={
                "symbol": pl.col("src_code").str.split(".").list.get(0),
                "exchange": pl.col("src_code").str.split(".").list.get(1),
            },
        )

        # 验证 computed_columns 的键（因为 Expr 对象不能直接用 == 比较）
        assert set(mapping.computed_columns.keys()) == {"symbol", "exchange"}
        assert isinstance(mapping.computed_columns["symbol"], pl.Expr)
        assert isinstance(mapping.computed_columns["exchange"], pl.Expr)

        # 验证默认值为空字典
        default_mapping = ColumnMapping(rename={}, date_columns={}, float_columns=[])
        assert default_mapping.computed_columns == {}

        # 验证 computed_columns 是独立的（不共享可变默认值）
        mapping1 = ColumnMapping(
            rename={},
            date_columns={},
            float_columns=[],
            computed_columns={"a": pl.lit(1)},
        )
        mapping2 = ColumnMapping(rename={}, date_columns={}, float_columns=[])
        assert mapping2.computed_columns == {}
        assert "a" not in mapping2.computed_columns
        # mapping1 应该有自己的 computed_columns
        assert "a" in mapping1.computed_columns


class TestTushareDataTransformer:
    """Tests for TushareDataTransformer."""

    def test_transform_daily_ohlcv_with_data(self) -> None:
        """Test transform_daily_ohlcv with actual data."""
        # 创建输入 DataFrame（模拟 Tushare API 返回）
        input_df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "trade_date": ["20240102", "20240102"],
                "open": ["11.5", "10.2"],
                "high": ["11.8", "10.5"],
                "low": ["11.3", "10.1"],
                "close": ["11.6", "10.4"],
                "pre_close": ["11.5", "10.2"],
                "vol": ["12500000", "8000000"],
                "amount": ["145000000", "83000000"],
                "pct_chg": ["0.87", "1.96"],
            }
        )

        # 执行转换
        result = TushareDataTransformer.transform_daily_ohlcv(
            input_df, "test_dataset", DAILY_OHLCV_MAPPING
        )

        # 验证 schema
        assert result.schema == {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }

        # 验证数据
        assert result.to_dicts() == [
            {
                "src_code": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "open": 11.5,
                "high": 11.8,
                "low": 11.3,
                "close": 11.6,
                "pre_close": 11.5,
                "volume": 12500000.0,
                "amount": 145000000.0,
                "pct_change": 0.87,
            },
            {
                "src_code": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "open": 10.2,
                "high": 10.5,
                "low": 10.1,
                "close": 10.4,
                "pre_close": 10.2,
                "volume": 8000000.0,
                "amount": 83000000.0,
                "pct_change": 1.96,
            },
        ]

    def test_transform_daily_ohlcv_empty_dataframe(self) -> None:
        """Test transform_daily_ohlcv with empty DataFrame."""
        input_df = pl.DataFrame(
            schema={
                "ts_code": pl.String,
                "trade_date": pl.String,
                "open": pl.String,
                "high": pl.String,
                "low": pl.String,
                "close": pl.String,
                "pre_close": pl.String,
                "vol": pl.String,
                "amount": pl.String,
                "pct_chg": pl.String,
            }
        )

        result = TushareDataTransformer.transform_daily_ohlcv(
            input_df, "test_dataset", DAILY_OHLCV_MAPPING
        )

        # 验证返回正确 schema 的空 DataFrame
        assert result.is_empty()
        assert result.schema == {
            "src_code": pl.String,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }
