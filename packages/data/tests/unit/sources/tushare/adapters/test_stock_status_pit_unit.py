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
                assert params["suspend_date"] == "20180615"
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH"],
                        "suspend_timing": ["09:30-15:00"],
                    }
                )
            case "stock_st":
                assert params["trade_date"] == "20180615"
                return pl.DataFrame(schema={"ts_code": pl.String, "name": pl.String})
            case "bak_basic":
                assert params["trade_date"] == "20180615"
                return pl.DataFrame(
                    {
                        "ts_code": ["600000.SH", "600001.SH"],
                        "name": ["浦发银行", "*ST示例"],
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
