"""Tests for TushareDataTransformer."""

from datetime import date

import polars as pl
from ditto_data.sources.normalization import NormalizationConfig
from ditto_data.sources.tushare.processors.mappings import (
    ADJ_FACTOR_MAPPING,
    CALENDAR_MAPPING,
    DAILY_OHLCV_MAPPING,
    ETF_BASIC_MAPPING,
)
from ditto_data.sources.tushare.processors.transformer import (
    ColumnMapping,
    TushareDataTransformer,
)


class TestColumnMapping:
    """Tests for ColumnMapping dataclass."""

    def test_column_mapping_creation(self) -> None:
        """Test creating a ColumnMapping instance."""
        mapping = ColumnMapping(
            rename={"ts_code": "source_ticker", "vol": "volume"},
            date_columns={"trade_date": "%Y%m%d"},
            float_columns=["open", "high", "low", "close"],
        )

        assert mapping.rename == {"ts_code": "source_ticker", "vol": "volume"}
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
        # Verify默认值为空元组
        default_mapping = ColumnMapping(rename={}, date_columns={}, float_columns=[])
        assert default_mapping.boolean_columns == ()

    def test_column_mapping_with_computed_columns(self) -> None:
        """Test ColumnMapping with computed_columns field."""
        # [REVIEW] computed_columns 的映射配置
        mapping = ColumnMapping(
            rename={"ts_code": "source_ticker"},
            date_columns={},
            float_columns=[],
            computed_columns={
                "ticker": pl.col("source_ticker").str.split(".").list.get(0),
                "exchange": pl.col("source_ticker").str.split(".").list.get(1),
            },
        )

        # Verify computed_columns 的键(因为 Expr 对象不能直接用 == 比较)
        assert set(mapping.computed_columns.keys()) == {"ticker", "exchange"}
        assert isinstance(mapping.computed_columns["ticker"], pl.Expr)
        assert isinstance(mapping.computed_columns["exchange"], pl.Expr)

        # Verify默认值为空字典
        default_mapping = ColumnMapping(rename={}, date_columns={}, float_columns=[])
        assert default_mapping.computed_columns == {}

        # Verify computed_columns 是独立的(不共享可变默认值)
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

    def test_column_mapping_with_normalization(self) -> None:
        """Test ColumnMapping with normalization field."""
        config = NormalizationConfig(
            amount_multiplier=10000.0,
            volume_multiplier=100.0,
            percentage_as_decimal=True,
        )

        mapping = ColumnMapping(
            rename={},
            date_columns={},
            float_columns=[],
            normalization=config,
        )

        assert mapping.normalization == config
        assert mapping.normalization is not None
        assert mapping.normalization.amount_multiplier == 10000.0
        assert mapping.normalization.volume_multiplier == 100.0

    def test_column_mapping_normalization_attribute(self) -> None:
        """Test ColumnMapping normalization attribute access."""
        config = NormalizationConfig(
            amount_multiplier=1.0,
            volume_multiplier=1.0,
        )

        mapping = ColumnMapping(
            rename={},
            date_columns={},
            float_columns=[],
            normalization=config,
        )

        assert mapping.normalization == config
        assert mapping.normalization is not None


class TestTushareDataTransformer:
    """Tests for TushareDataTransformer."""

    def test_transform_daily_ohlcv_with_data(self) -> None:
        """Test transform_daily_ohlcv with actual data."""
        # [REVIEW] DataFrame(模拟 Tushare API 返回)
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

        # [REVIEW]
        result = TushareDataTransformer.transform_daily_ohlcv(
            input_df, "test_dataset", DAILY_OHLCV_MAPPING
        )

        # Verify schema
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }

        # Verify数据
        assert result.to_dicts() == [
            {
                "source_ticker": "000001.SZ",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 3),
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
                "source_ticker": "600000.SH",
                "trade_date": date(2024, 1, 2),
                "knowledge_date": date(2024, 1, 3),
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

        # Verify返回正确 schema 的空 DataFrame
        assert len(result) == 0
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "pre_close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "pct_change": pl.Float64,
        }

    def test_transform_with_boolean_columns(self) -> None:
        """Test transform with boolean type columns conversion."""
        # [REVIEW] Tushare API 返回的交易日历数据
        # is_open 字段是整数 0/1，需要转换为 pl.Boolean
        input_df = pl.DataFrame(
            {
                "cal_date": ["20240102", "20240103", "20240104", "20240105"],
                "is_open": [1, 1, 0, 0],  # [REVIEW]1=开市，0=休市
            }
        )

        # [REVIEW] transform() 方法
        # [REVIEW]
        result = TushareDataTransformer.transform(
            input_df, "calendar", CALENDAR_MAPPING
        )

        # Verify schema
        assert dict(result.schema) == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

        # Verify数据转换正确
        assert result.to_dicts() == [
            {"trade_date": date(2024, 1, 2), "is_open": True},
            {"trade_date": date(2024, 1, 3), "is_open": True},
            {"trade_date": date(2024, 1, 4), "is_open": False},
            {"trade_date": date(2024, 1, 5), "is_open": False},
        ]

    def test_transform_with_computed_columns(self) -> None:
        """Test transform with computed columns (ticker/exchange extraction)."""
        # [REVIEW] Tushare API 返回的 ETF 基本信息数据
        input_df = pl.DataFrame(
            {
                "ts_code": ["510300.SH", "159919.SZ", "512100.SH"],
                "name": ["沪深300ETF", "沪深300ETF", "科创板50ETF"],
                "list_date": ["20120706", "20190624", "20201116"],
            }
        )

        # [REVIEW] transform() 方法
        # [REVIEW]
        result = TushareDataTransformer.transform(
            input_df, "etf_basic", ETF_BASIC_MAPPING
        )

        # Verify schema
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "ticker": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify数据转换正确
        assert result.to_dicts() == [
            {
                "source_ticker": "510300.SH",
                "ticker": "510300",
                "name": "沪深300ETF",
                "exchange": "SSE",
                "list_date": date(2012, 7, 6),
            },
            {
                "source_ticker": "159919.SZ",
                "ticker": "159919",
                "name": "沪深300ETF",
                "exchange": "SZSE",
                "list_date": date(2019, 6, 24),
            },
            {
                "source_ticker": "512100.SH",
                "ticker": "512100",
                "name": "科创板50ETF",
                "exchange": "SSE",
                "list_date": date(2020, 11, 16),
            },
        ]

    def test_transform_calendar_empty(self) -> None:
        """Test transform with empty calendar DataFrame."""
        # [REVIEW] DataFrame，但有正确的 schema
        input_df = pl.DataFrame(schema={"cal_date": pl.String, "is_open": pl.Int64})

        # [REVIEW] transform() 方法
        result = TushareDataTransformer.transform(
            input_df, "calendar", CALENDAR_MAPPING
        )

        # Verify返回正确 schema 的空 DataFrame
        assert result.is_empty()
        assert dict(result.schema) == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

    def test_transform_adj_factor_empty(self) -> None:
        """Test transform with empty adj_factor DataFrame."""
        # [REVIEW] DataFrame，但有正确的 schema
        input_df = pl.DataFrame(
            schema={
                "ts_code": pl.String,
                "trade_date": pl.String,
                "adj_factor": pl.String,
            }
        )

        # [REVIEW] transform() 方法
        result = TushareDataTransformer.transform(
            input_df, "adj_factor", ADJ_FACTOR_MAPPING
        )

        # Verify返回正确 schema 的空 DataFrame
        assert result.is_empty()
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }

    def test_transform_etf_basic_empty(self) -> None:
        """
        Test transform with empty ETF basic DataFrame - computed columns type
        inference.
        """
        # [REVIEW] DataFrame，但有正确的 schema
        input_df = pl.DataFrame(
            schema={
                "ts_code": pl.String,
                "name": pl.String,
                "list_date": pl.String,
            }
        )

        # [REVIEW] transform() 方法
        result = TushareDataTransformer.transform(
            input_df, "etf_basic", ETF_BASIC_MAPPING
        )

        # Verify返回正确 schema 的空 DataFrame
        # [REVIEW]: ticker 和 exchange 是 computed_columns,类型应该是 pl.String
        assert result.is_empty()
        assert dict(result.schema) == {
            "source_ticker": pl.String,
            "ticker": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }
