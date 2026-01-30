"""SourceSchema 集成测试：真实 Tushare API 数据验证

测试 SourceSchema 与真实 Tushare API 返回数据的兼容性。

运行方式：
    pytest -m integration

前置条件：
    - TUSHARE_TOKEN 环境变量已设置
    - 网络连接正常
"""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.sources.source_schema import SourceSchema
from ditto_datahub.sources.tushare.tushare_source import TushareSource


@pytest.mark.integration
class TestSourceSchemaWithRealAPI:
    """测试 SourceSchema 与真实 Tushare API 数据的兼容性"""

    def test_calendar_schema_with_real_data(self) -> None:
        """测试交易日历数据的 SourceSchema 验证"""
        # 定义交易日历的 SourceSchema
        calendar_schema = SourceSchema(
            dataset="calendar",
            key_columns=("trade_date",),
            schema={
                "trade_date": pl.Date,
                "is_open": pl.Boolean,
            },
        )

        # 获取真实数据
        source = TushareSource()
        calendar = source.fetch_calendar("2024-01-01", "2024-01-05")

        # 验证 Schema
        calendar_schema.validate(calendar)

        # 额外验证：确保数据符合预期
        assert calendar.height > 0, "Calendar 数据不应为空"
        assert "trade_date" in calendar.columns
        assert "is_open" in calendar.columns

    def test_stock_basic_schema_with_real_data(self) -> None:
        """测试股票基本信息的 SourceSchema 验证"""
        # 定义股票基本信息的 SourceSchema
        stock_basic_schema = SourceSchema(
            dataset="stock_basic",
            key_columns=("src_code",),
            schema={
                "src_code": pl.String,
                "symbol": pl.String,
                "name": pl.String,
                "exchange": pl.String,
                "list_date": pl.Date,
            },
        )

        # 获取真实数据
        source = TushareSource()
        stocks = source.fetch_stock_basic()

        # 验证 Schema
        stock_basic_schema.validate(stocks)

        # 额外验证
        assert stocks.height > 0, "Stock basic 数据不应为空"
        assert set(stocks.columns) == {
            "src_code",
            "symbol",
            "name",
            "exchange",
            "list_date",
        }

    def test_stock_daily_schema_with_real_data(self) -> None:
        """测试日线行情数据的 SourceSchema 验证"""
        # 定义日线行情的 SourceSchema
        daily_schema = SourceSchema(
            dataset="stock_daily",
            key_columns=("src_code", "trade_date"),
            schema={
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
            },
        )

        # 获取真实数据
        source = TushareSource()
        daily = source.fetch_stock_daily("2024-01-02")

        # 验证 Schema
        daily_schema.validate(daily)

        # 额外验证
        assert daily.height > 0, "Daily 数据不应为空"
        assert set(daily.columns) == {
            "src_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
            "pct_change",
        }

        # 验证 OHLC 逻辑
        for row in daily.to_dicts():
            assert row["high"] >= row["low"], "High 价应 >= Low 价"
            assert row["high"] >= row["open"], "High 价应 >= Open 价"
            assert row["high"] >= row["close"], "High 价应 >= Close 价"
            assert row["low"] <= row["open"], "Low 价应 <= Open 价"
            assert row["low"] <= row["close"], "Low 价应 <= Close 价"

    def test_etf_basic_schema_with_real_data(self) -> None:
        """测试 ETF 基本信息的 SourceSchema 验证"""
        # 定义 ETF 基本信息的 SourceSchema
        etf_basic_schema = SourceSchema(
            dataset="etf_basic",
            key_columns=("src_code",),
            schema={
                "src_code": pl.String,
                "symbol": pl.String,
                "name": pl.String,
                "exchange": pl.String,
                "list_date": pl.Date,
            },
        )

        # 获取真实数据
        source = TushareSource()
        etf_basic = source.fetch_etf_basic()

        # 验证 Schema
        etf_basic_schema.validate(etf_basic)

        # 额外验证
        assert etf_basic.height > 0, "ETF basic 数据不应为空"
        assert set(etf_basic.columns) == {
            "src_code",
            "symbol",
            "name",
            "exchange",
            "list_date",
        }

    def test_etf_daily_schema_with_real_data(self) -> None:
        """测试 ETF 日线行情的 SourceSchema 验证"""
        # 定义 ETF 日线行情的 SourceSchema
        etf_daily_schema = SourceSchema(
            dataset="etf_daily",
            key_columns=("src_code", "trade_date"),
            schema={
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
            },
        )

        # 获取真实数据
        source = TushareSource()
        etf_daily = source.fetch_etf_daily("2024-01-02")

        # 验证 Schema
        etf_daily_schema.validate(etf_daily)

        # 额外验证
        assert etf_daily.height > 0, "ETF daily 数据不应为空"

    def test_adj_factor_schema_with_real_data(self) -> None:
        """测试复权因子的 SourceSchema 验证"""
        # 定义复权因子的 SourceSchema（带 knowledge_date）
        adj_factor_schema = SourceSchema(
            dataset="adj_factor",
            key_columns=("src_code", "trade_date"),
            schema={
                "src_code": pl.String,
                "trade_date": pl.Date,
                "knowledge_date": pl.Date,
                "adj_factor": pl.Float64,
            },
        )

        # 获取真实数据
        source = TushareSource()
        adj_factor = source.fetch_adj_factor("2024-01-02")

        # 验证 Schema
        adj_factor_schema.validate(adj_factor)

        # 额外验证
        assert adj_factor.height > 0, "Adj factor 数据不应为空"

        # 验证 knowledge_date 逻辑
        for row in adj_factor.to_dicts():
            assert row["knowledge_date"] == row["trade_date"], (
                "knowledge_date 应等于 trade_date"
            )

    def test_stock_limit_schema_with_real_data(self) -> None:
        """测试涨跌停价的 SourceSchema 验证"""
        # 定义涨跌停价的 SourceSchema
        stock_limit_schema = SourceSchema(
            dataset="stock_limit",
            key_columns=("src_code", "trade_date"),
            schema={
                "src_code": pl.String,
                "trade_date": pl.Date,
                "up_limit": pl.Float64,
                "down_limit": pl.Float64,
            },
        )

        # 获取真实数据
        source = TushareSource()
        stock_limit = source.fetch_stock_limit("2024-01-02")

        # 验证 Schema
        stock_limit_schema.validate(stock_limit)

        # 额外验证
        assert stock_limit.height > 0, "Stock limit 数据不应为空"

        # 验证涨跌停价逻辑
        for row in stock_limit.to_dicts():
            assert row["up_limit"] > row["down_limit"], "涨停价应大于跌停价"
            assert row["up_limit"] > 0, "涨停价应大于 0"
            assert row["down_limit"] > 0, "跌停价应大于 0"

    def test_stock_status_schema_with_real_data(self) -> None:
        """测试股票状态的 SourceSchema 验证

        注意：stock_status 数据源可能包含重复的主键（同一股票同一天多条状态记录），
        这是 Tushare API 的实际行为。因此这里只验证列的存在性和类型，不验证主键唯一性。
        """
        # 定义股票状态的 SourceSchema（不设置主键，允许重复）
        stock_status_schema = SourceSchema(
            dataset="stock_status",
            key_columns=(),  # 空主键，不验证唯一性
            schema={
                "src_code": pl.String,
                "trade_date": pl.Date,
                "is_suspended": pl.Boolean,
                "suspend_timing": pl.String,
                "is_st": pl.Boolean,
                "st_type": pl.String,
                "list_status": pl.String,
            },
        )

        # 获取真实数据
        source = TushareSource()
        stock_status = source.fetch_stock_status("2024-01-02")

        # 验证 Schema
        stock_status_schema.validate(stock_status)

        # 额外验证
        assert stock_status.height > 0, "Stock status 数据不应为空"

        # 验证布尔类型
        for row in stock_status.to_dicts():
            assert isinstance(row["is_suspended"], bool), "is_suspended 应为布尔值"
            assert isinstance(row["is_st"], bool), "is_st 应为布尔值"
            assert row["list_status"] in ["L", "D", "P"], "list_status 应为 L/D/P"

    def test_fund_adj_schema_with_real_data(self) -> None:
        """测试基金复权因子的 SourceSchema 验证"""
        # 定义基金复权因子的 SourceSchema
        fund_adj_schema = SourceSchema(
            dataset="fund_adj",
            key_columns=("src_code", "trade_date"),
            schema={
                "src_code": pl.String,
                "trade_date": pl.Date,
                "knowledge_date": pl.Date,
                "adj_factor": pl.Float64,
            },
        )

        # 获取真实数据
        source = TushareSource()
        fund_adj = source.fetch_fund_adj("2024-01-02")

        # 验证 Schema
        fund_adj_schema.validate(fund_adj)

        # 额外验证
        assert fund_adj.height > 0, "Fund adj 数据不应为空"


@pytest.mark.integration
class TestSourceSchemaEdgeCases:
    """测试 SourceSchema 边界情况"""

    def test_schema_with_empty_response(self) -> None:
        """测试空响应的 Schema 验证"""
        # 定义一个简单的 Schema
        test_schema = SourceSchema(
            dataset="test_empty",
            key_columns=("id",),
            schema={
                "id": pl.String,
                "value": pl.Float64,
            },
        )

        # 创建空 DataFrame（符合 schema）
        empty_df = pl.DataFrame(
            schema={
                "id": pl.String,
                "value": pl.Float64,
            }
        )

        # 应该通过验证
        test_schema.validate(empty_df)

    def test_schema_with_duplicate_keys_real_data(self) -> None:
        """测试重复主键的检测（模拟数据）"""
        # 定义 Schema
        test_schema = SourceSchema(
            dataset="test_duplicate",
            key_columns=("src_code", "trade_date"),
            schema={
                "src_code": pl.String,
                "trade_date": pl.Date,
                "value": pl.Float64,
            },
        )

        # 创建包含重复主键的 DataFrame
        duplicate_df = pl.DataFrame(
            {
                "src_code": ["000001.SZ", "000001.SZ"],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 2)],
                "value": [1.0, 2.0],
            }
        )

        # 应该抛出异常
        from ditto_datahub.errors import SchemaValidationError

        with pytest.raises(SchemaValidationError) as exc_info:
            test_schema.validate(duplicate_df)

        assert "Duplicate keys" in str(exc_info.value)


@pytest.mark.integration
class TestSourceSchemaPITSupport:
    """测试 SourceSchema 对 PIT 数据的支持"""

    def test_pit_schema_definition(self) -> None:
        """测试带 PIT 列的 Schema 定义"""
        # 定义一个 PIT Schema（示例）
        pit_schema = SourceSchema(
            dataset="index_member",
            key_columns=("index_id", "instrument_id", "effective_from"),
            schema={
                "index_id": pl.String,
                "instrument_id": pl.String,
                "weight": pl.Float64,
                "effective_from": pl.Date,
                "effective_to": pl.Date | None,  # type: ignore[valid-type]
            },
            pit_columns=("effective_from", "effective_to"),
        )

        # 创建符合 PIT Schema 的测试数据
        pit_df = pl.DataFrame(
            {
                "index_id": ["000001", "000001"],
                "instrument_id": ["600000.SSE", "600001.SSE"],
                "weight": [0.5, 0.3],
                "effective_from": [date(2024, 1, 1), date(2024, 1, 1)],
                "effective_to": [date(2024, 6, 1), None],
            }
        )

        # 应该通过验证
        pit_schema.validate(pit_df)

    def test_pit_schema_with_null_effective_to(self) -> None:
        """测试 PIT Schema 中 effective_to 为 null 的情况"""
        # 定义 PIT Schema
        pit_schema = SourceSchema(
            dataset="test_pit",
            key_columns=("instrument_id", "effective_from"),
            schema={
                "instrument_id": pl.String,
                "effective_from": pl.Date,
                "effective_to": pl.Date | None,  # type: ignore[valid-type]
                "value": pl.Float64,
            },
            pit_columns=("effective_from", "effective_to"),
        )

        # 创建包含 null effective_to 的数据（当前有效）
        current_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SSE"],
                "effective_from": [date(2024, 1, 1)],
                "effective_to": [None],  # 当前有效
                "value": [100.0],
            }
        )

        # 应该通过验证
        pit_schema.validate(current_df)
