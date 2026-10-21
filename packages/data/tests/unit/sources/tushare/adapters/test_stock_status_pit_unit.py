"""PIT-safe Tushare stock-status adapter tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter


def test_historical_status_uses_date_scoped_provider_queries() -> None:
    client = MagicMock()

    def query(**params):
        match params["api_name"]:
            case "suspend_d":
                # 官方接口无 suspend_date 参数（#585）：日期参数是 trade_date，
                # 且必须显式 suspend_type="S" 只取停牌行。
                assert params["trade_date"] == "20180615"
                assert params["suspend_type"] == "S"
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH"],
                        "trade_date": ["20180615"],
                        "suspend_timing": ["09:30-15:00"],
                    }
                )
            case "stock_st":
                assert params["trade_date"] == "20180615"
                return pl.DataFrame(
                    schema={
                        "ts_code": pl.String,
                        "name": pl.String,
                        "trade_date": pl.String,
                    }
                )
            case "bak_basic":
                assert params["trade_date"] == "20180615"
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH", "600001.SH"],
                        "name": ["浦发银行", "*ST示例"],
                        "trade_date": ["20180615", "20180615"],
                    }
                )
            case unexpected:
                pytest.fail(f"unexpected provider API: {unexpected}")

    client.query.side_effect = query
    adapter = StockTushareAdapter(_client=client)

    result = adapter.fetch_stock_status("2018-06-15").sort("source_ticker")

    assert result["source_ticker"].to_list() == ["600000.SH", "600001.SH"]
    assert result["trade_date"].cast(pl.String).to_list() == [
        "2018-06-15",
        "2018-06-15",
    ]
    assert result["list_status"].to_list() == ["L", "L"]
    assert result["is_suspended"].to_list() == [True, False]
    assert result["is_st"].to_list() == [False, True]
    assert all(
        call.kwargs["api_name"] != "stock_basic" for call in client.query.call_args_list
    )


def test_suspend_fill_to_limit_rows_are_deduped() -> None:
    """代理 fill-to-limit：停牌名单重复填充行按 ts_code 去重后才是干净名单."""
    client = MagicMock()

    def query(**params):
        match params["api_name"]:
            case "suspend_d":
                # 同一 ts_code 重复三行（代理填充形态）
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH"] * 3,
                        "trade_date": ["20260930"] * 3,
                        "suspend_timing": ["09:30-15:00"] * 3,
                    }
                )
            case "stock_st":
                return pl.DataFrame(
                    schema={
                        "ts_code": pl.String,
                        "name": pl.String,
                        "trade_date": pl.String,
                    }
                )
            case "bak_basic":
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH"],
                        "name": ["浦发银行"],
                        "trade_date": ["20260930"],
                    }
                )
            case unexpected:
                pytest.fail(f"unexpected provider API: {unexpected}")

    client.query.side_effect = query
    adapter = StockTushareAdapter(_client=client)

    result = adapter.fetch_stock_status("2026-09-30")

    assert result.height == 1
    assert result["is_suspended"].to_list() == [True]


def test_suspend_foreign_dates_fail_closed() -> None:
    """#585：日期过滤失效（响应行落在请求日之外）必须 fail closed 拒绝入库."""
    client = MagicMock()

    def query(**params):
        match params["api_name"]:
            case "suspend_d":
                return pl.DataFrame(
                    {
                        "ts_code": ["000426.SZ"],
                        "trade_date": ["19990504"],
                        "suspend_timing": [None],
                    }
                )
            case unexpected:
                pytest.fail(f"unexpected provider API: {unexpected}")

    client.query.side_effect = query
    adapter = StockTushareAdapter(_client=client)

    with pytest.raises(SourceFetchError) as exc_info:
        adapter.fetch_stock_status("2026-09-30")

    # fetch_stock_status 的错误包装器保留消息与 cause 链；外域日期证据在
    # 守卫错误的 details 里（经 __cause__ 可达）。
    combined = str(exc_info.value) + str(exc_info.value.details)
    assert "suspend_d" in combined
    cause = exc_info.value.__cause__
    assert isinstance(cause, SourceFetchError)
    assert cause.details["expected_trade_date"] == "20260930"
    assert cause.details["foreign_trade_dates"] == ["19990504"]


def test_pre_2016_stock_status_fails_closed() -> None:
    client = MagicMock()
    adapter = StockTushareAdapter(_client=client)

    with pytest.raises(SourceFetchError, match="2016-01-01"):
        adapter.fetch_stock_status("2015-12-31")

    client.query.assert_not_called()


def test_component_fetch_error_does_not_turn_into_false_statuses() -> None:
    client = MagicMock()

    def query(**params):
        if params["api_name"] == "suspend_d":
            raise SourceFetchError("suspend unavailable", "tushare")
        if params["api_name"] == "bak_basic":
            return pl.DataFrame({"ts_code": ["600000.SH"], "name": ["浦发银行"]})
        return pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})

    client.query.side_effect = query
    adapter = StockTushareAdapter(_client=client)

    with pytest.raises(SourceFetchError, match="stock_status"):
        adapter.fetch_stock_status("2018-06-15")


def test_suspend_same_code_different_timing_rows_survive() -> None:
    """整行去重（correctness review #196）：同股不同 suspend_timing 是真实两行."""
    client = MagicMock()

    def query(**params):
        match params["api_name"]:
            case "suspend_d":
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH", "600000.SH"],
                        "trade_date": ["20260930", "20260930"],
                        "suspend_timing": ["上午", "全天"],
                    }
                )
            case "stock_st":
                return pl.DataFrame(
                    schema={
                        "ts_code": pl.String,
                        "name": pl.String,
                        "trade_date": pl.String,
                    }
                )
            case "bak_basic":
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH"],
                        "name": ["浦发银行"],
                        "trade_date": ["20260930"],
                    }
                )
            case unexpected:
                pytest.fail(f"unexpected provider API: {unexpected}")

    client.query.side_effect = query
    adapter = StockTushareAdapter(_client=client)

    result = adapter.fetch_stock_status("2026-09-30")

    assert result.height == 1
    assert result["is_suspended"].to_list() == [True]
