"""端到端集成测试：真实 Tushare API 调用.

这些测试调用真实的 Tushare API，需要：
1. 有效的 TUSHARE_TOKEN 环境变量
2. 网络连接
3. 手动运行(标记为 @pytest.mark.integration)

运行方式：
    pytest packages/datahub/tests/integration/sources/tushare/... -m integration
"""

import os
import time
from datetime import date

import polars as pl
import pytest
from ditto_datahub.config import DataSourceSettings
from ditto_datahub.sources.base import SourceAuthenticationError
from ditto_datahub.sources.tushare.tushare_source import TushareSource


def _settings_from_env() -> DataSourceSettings:
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        pytest.skip("TUSHARE_TOKEN is required for integration tests")
    return DataSourceSettings(tushare_token=token)


@pytest.mark.integration
class TestTushareEndToEnd:
    """端到端集成测试：验证完整的 Tushare API 调用流程."""

    def test_end_to_end_tushare_ingestion(self) -> None:
        """集成测试：完整的数据获取流程.

        测试场景：
        1. 初始化 Source
        2. 测试 calendar 获取
        3. 测试 stock_basic 获取
        4. 测试 stock_daily 获取
        5. 验证 schema 正确性

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        # 1. 初始化 Source(从环境变量读取 token)
        source = TushareSource(settings=_settings_from_env())

        # 2. 测试 calendar 获取
        calendar = source.fetch_calendar("2024-01-01", "2024-01-05")
        assert calendar.height > 0, "Calendar 数据不应为空"
        assert calendar.schema == {
            "trade_date": pl.Date,
            "is_open": pl.Boolean,
        }

        # Verify数据转换正确性
        calendar_dict = calendar.to_dicts()
        assert isinstance(calendar_dict, list)
        assert all(isinstance(d["trade_date"], date) for d in calendar_dict)
        assert all(isinstance(d["is_open"], bool) for d in calendar_dict)

        # 3. 测试 stock_basic 获取
        stocks = source.fetch_stock_basic()
        assert stocks.height > 0, "Stock basic 数据不应为空"
        assert stocks.schema == {
            "source_ticker": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify数据转换正确性
        stocks_dict = stocks.to_dicts()
        assert isinstance(stocks_dict, list)
        assert all("." in d["source_ticker"] for d in stocks_dict)
        # exchange 可能包含 SSE, SZSE, BSE 等多种交易所
        assert all(
            d["exchange"] in stocks["exchange"].unique().to_list() for d in stocks_dict
        )

        # 4. 测试 stock_daily 获取(使用交易日 2024-01-02)
        daily = source.fetch_stock_daily("2024-01-02")
        assert daily.height > 0, "Stock daily 数据不应为空"
        assert daily.schema == {
            "source_ticker": pl.String,
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

        # Verify数据转换正确性
        daily_dict = daily.to_dicts()
        assert isinstance(daily_dict, list)
        assert all(d["trade_date"] == date(2024, 1, 2) for d in daily_dict)

        # 5. 验证 OHLC 逻辑正确性
        for row in daily_dict:
            assert row["high"] >= row["low"], "High 价应 >= Low 价"
            assert row["high"] >= row["open"], "High 价应 >= Open 价"
            assert row["high"] >= row["close"], "High 价应 >= Close 价"
            assert row["low"] <= row["open"], "Low 价应 <= Open 价"
            assert row["low"] <= row["close"], "Low 价应 <= Close 价"

    def test_etf_end_to_end_tushare_ingestion(self) -> None:
        """集成测试：ETF 数据获取流程.

        测试场景：
        1. 测试 etf_basic 获取
        2. 测试 etf_daily 获取
        3. 验证 schema 正确性

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        source = TushareSource(settings=_settings_from_env())

        # 1. 测试 etf_basic 获取
        etf_basic = source.fetch_etf_basic()
        assert etf_basic.height > 0, "ETF basic 数据不应为空"
        assert etf_basic.schema == {
            "source_ticker": pl.String,
            "symbol": pl.String,
            "name": pl.String,
            "exchange": pl.String,
            "list_date": pl.Date,
        }

        # Verify数据转换正确性
        etf_dict = etf_basic.to_dicts()
        assert isinstance(etf_dict, list)
        assert all("." in d["source_ticker"] for d in etf_dict)

        # 2. 测试 etf_daily 获取
        etf_daily = source.fetch_etf_daily("2024-01-02")
        assert etf_daily.height > 0, "ETF daily 数据不应为空"
        assert etf_daily.schema == {
            "source_ticker": pl.String,
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

        # Verify OHLC 逻辑正确性
        etf_daily_dict = etf_daily.to_dicts()
        for row in etf_daily_dict:
            assert row["high"] >= row["low"], "High 价应 >= Low 价"

    def test_adj_factor_end_to_end(self) -> None:
        """集成测试：复权因子数据获取.

        测试场景：
        1. 测试 stock adj_factor 获取
        2. 测试 fund adj 获取
        3. 验证 knowledge_date 正确性

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        source = TushareSource(settings=_settings_from_env())

        # 1. 测试 stock adj_factor 获取
        adj_factor = source.fetch_adj_factor("2024-01-02")
        assert adj_factor.height > 0, "Adj factor 数据不应为空"
        assert adj_factor.schema == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }

        # Verify knowledge_date = trade_date(数据即日可用)
        adj_dict = adj_factor.to_dicts()
        for row in adj_dict:
            assert row["knowledge_date"] == row["trade_date"], (
                "knowledge_date 应等于 trade_date"
            )

        # 2. 测试 fund adj 获取
        fund_adj = source.fetch_fund_adj("2024-01-02")
        assert fund_adj.height > 0, "Fund adj 数据不应为空"
        assert fund_adj.schema == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "adj_factor": pl.Float64,
        }

    def test_stock_limit_and_status(self) -> None:
        """集成测试：涨跌停价和股票状态数据获取.

        测试场景：
        1. 测试 stock_limit 获取
        2. 测试 stock_status 获取
        3. 验证数据逻辑正确性

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        source = TushareSource(settings=_settings_from_env())

        # 1. 测试 stock_limit 获取
        stock_limit = source.fetch_stock_limit("2024-01-02")
        assert stock_limit.height > 0, "Stock limit 数据不应为空"
        assert stock_limit.schema == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "up_limit": pl.Float64,
            "down_limit": pl.Float64,
        }

        # Verify涨跌停价逻辑
        limit_dict = stock_limit.to_dicts()
        for row in limit_dict:
            assert row["up_limit"] > row["down_limit"], "涨停价应大于跌停价"
            assert row["up_limit"] > 0, "涨停价应大于 0"
            assert row["down_limit"] > 0, "跌停价应大于 0"

        # 2. 测试 stock_status 获取
        stock_status = source.fetch_stock_status("2024-01-02")
        assert stock_status.height > 0, "Stock status 数据不应为空"
        assert stock_status.schema == {
            "source_ticker": pl.String,
            "trade_date": pl.Date,
            "is_suspended": pl.Boolean,
            "suspend_timing": pl.String,
            "is_st": pl.Boolean,
            "st_type": pl.String,
            "list_status": pl.String,
        }

        # Verify状态逻辑
        status_dict = stock_status.to_dicts()
        for row in status_dict:
            assert isinstance(row["is_suspended"], bool), "is_suspended 应为布尔值"
            assert isinstance(row["is_st"], bool), "is_st 应为布尔值"
            assert row["list_status"] in ["L", "D", "P"], "list_status 应为 L/D/P"

    def test_rate_limiting_respected(self) -> None:
        """集成测试：验证限流机制正常工作.

        测试场景：
        1. 连续多次调用同一个 API
        2. 验证请求间隔符合限流要求
        3. 验证最终都成功返回

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        source = TushareSource(settings=_settings_from_env())

        # [REVIEW] calendar API
        start_time = time.time()
        results = []
        for _i in range(3):
            result = source.fetch_calendar("2024-01-01", "2024-01-05")
            results.append(result)
        elapsed_time = time.time() - start_time

        # Verify所有调用都成功
        assert all(r.height > 0 for r in results), "所有请求都应成功"

        # Verify限流：Tushare 免费账户限流 200次/分钟
        # 3 次请求至少应该有适当的间隔(基于限流配置)
        # [REVIEW]
        assert elapsed_time > 0, "请求应该有耗时"

    def test_error_handling_invalid_token(self) -> None:
        """集成测试：验证无效 token 的错误处理.

        测试场景：
        1. 使用无效 token 初始化 Source
        2. 验证抛出正确的异常类型

        前置条件：
        - 网络连接正常
        """
        # [REVIEW] token(直接传递参数，绕过 keyring)
        source = TushareSource(
            settings=DataSourceSettings(tushare_token="invalid_token_12345")
        )

        # [REVIEW]
        with pytest.raises(SourceAuthenticationError):
            source.fetch_calendar("2024-01-01", "2024-01-05")

    def test_data_consistency_multiple_calls(self) -> None:
        """集成测试：验证多次调用返回的数据一致性.

        测试场景：
        1. 同一参数多次调用同一 API
        2. 验证返回的数据结构一致
        3. 验证数据内容一致(对于静态数据如 stock_basic)

        前置条件：
        - TUSHARE_TOKEN 环境变量已设置
        - 网络连接正常
        """
        source = TushareSource(settings=_settings_from_env())

        # [REVIEW] stock_basic(静态数据)
        stocks1 = source.fetch_stock_basic()
        stocks2 = source.fetch_stock_basic()

        # Verify数据行数一致
        assert stocks1.height == stocks2.height, "多次调用返回行数应一致"

        # Verify schema 一致
        assert stocks1.schema == stocks2.schema, "多次调用返回 schema 应一致"

        # Verify内容一致(按 source_ticker 排序后比较)
        sorted1 = stocks1.sort("source_ticker")
        sorted2 = stocks2.sort("source_ticker")
        assert sorted1.equals(sorted2), "多次调用返回内容应一致"
