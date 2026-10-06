"""Tests for index_dailybasic adapter（#434 指数估值，市值元/股本股）."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.capital_market import (
    INDEX_VALUATION_SCHEMA,
)

_INDEX_DAILYBASIC_FIELDS = (
    "ts_code,trade_date,total_mv,float_mv,pe,pe_ttm,pb,turnover_rate"
)


def _client() -> MagicMock:
    client = MagicMock()
    client.query.return_value = pl.DataFrame(
        {
            "ts_code": ["000001.SH", "000300.SH"],
            "trade_date": ["20260930", "20260930"],
            "total_mv": [75834902899483.61, 61000000000000.0],
            "float_mv": [59426309161634.28, 55000000000000.0],
            "pe": [16.7974, None],
            "pe_ttm": [15.6128, 13.2],
            "pb": [1.4305, 1.35],
            "turnover_rate": [0.8434, 0.92],
        }
    )
    return client


@pytest.mark.unit
class TestIndexValuation:
    def test_request_uses_documented_field_set(self) -> None:
        from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter

        # adapter._client 静态收窄为 TushareClient；断言走 mock 边界变量。
        client = _client()
        adapter = CapitalTushareAdapter(_client=client)
        adapter.fetch_index_valuation(trade_date="2026-09-30")

        kwargs = client.query.call_args.kwargs
        assert kwargs["api_name"] == "index_dailybasic"
        assert set(kwargs["fields"].split(",")) == set(
            _INDEX_DAILYBASIC_FIELDS.split(",")
        )
        assert kwargs["trade_date"] == "20260930"

    def test_market_cap_kept_in_yuan_and_missing_pe_kept_null(self) -> None:
        """市值按元原值保留（不套万元换算）；缺 PE 保留 null 不填零。"""
        from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter

        adapter = CapitalTushareAdapter(_client=_client())
        result = adapter.fetch_index_valuation(trade_date="2026-09-30")

        assert result.columns == list(INDEX_VALUATION_SCHEMA)
        row = result.filter(pl.col("source_ticker") == "000001.SH").to_dicts()[0]
        assert row["total_mv"] == 75834902899483.61
        assert row["knowledge_date"] == date.today()
        hs300 = result.filter(pl.col("source_ticker") == "000300.SH").to_dicts()[0]
        assert hs300["pe"] is None

    def test_empty_coverage_reports_empty_not_zero(self) -> None:
        """端点不覆盖的指数日返回空帧，不造零行。"""
        from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter

        client = MagicMock()
        client.query.return_value = pl.DataFrame()
        adapter = CapitalTushareAdapter(_client=client)

        result = adapter.fetch_index_valuation(trade_date="2026-10-04")

        assert result.height == 0
        assert result.columns == list(INDEX_VALUATION_SCHEMA)
