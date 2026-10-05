"""Tests for earnings forecast/express adapters（#434 业绩预告与快报）."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.fundamental import (
    EARNINGS_EXPRESS_SCHEMA,
    EARNINGS_FORECAST_SCHEMA,
    FundamentalTushareAdapter,
)


@pytest.mark.unit
class TestEarningsForecast:
    def test_ann_date_mode_uses_vip_endpoint(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = _forecast_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_forecast(ann_date="2026-01-30")

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["api_name"] == "forecast_vip"
        assert kwargs["ann_date"] == "20260130"
        assert result.height == 3  # 000017.SZ 两个修订版本 + 000048.SZ

    def test_same_day_update_flag_versions_are_both_kept(self) -> None:
        """同日 update_flag 0/1 两行是独立修订版本，不去重。"""
        mock_client = MagicMock()
        mock_client.query.return_value = _forecast_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_forecast(ann_date="2026-01-30")

        flags = result.filter(pl.col("source_ticker") == "000017.SZ")[
            "update_flag"
        ].to_list()
        assert sorted(flags) == ["0", "1"]

    def test_profit_bounds_kept_raw_in_wan_yuan(self) -> None:
        """净利润上下限按万元原值保留，不换算。"""
        mock_client = MagicMock()
        mock_client.query.return_value = _forecast_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_forecast(ann_date="2026-01-30")

        row = result.filter(
            (pl.col("source_ticker") == "000017.SZ") & (pl.col("update_flag") == "0")
        ).to_dicts()[0]
        assert row["net_profit_min"] == 3600.0
        assert row["net_profit_max"] == 5400.0
        assert row["forecast_type"] == "预增"
        assert row["first_ann_date"] == date(2026, 1, 30)
        assert row["report_date"] == date(2025, 12, 31)

    def test_ticker_mode_requires_ticker(self) -> None:
        adapter = FundamentalTushareAdapter(_client=MagicMock())
        with pytest.raises(ValueError, match="source_ticker"):
            adapter.fetch_earnings_forecast(start_date="2024-01-01")

    def test_empty_response_returns_schema_frame(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_forecast(ann_date="2026-03-30")

        assert result.height == 0
        assert result.columns == list(EARNINGS_FORECAST_SCHEMA)


@pytest.mark.unit
class TestEarningsExpress:
    def test_ann_date_mode_uses_vip_endpoint(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = _express_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_express(ann_date="2026-01-30")

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["api_name"] == "express_vip"
        assert kwargs["ann_date"] == "20260130"
        assert result.height == 1

    def test_amounts_kept_raw_in_yuan(self) -> None:
        """金额按元原值保留，不换算为万元。"""
        mock_client = MagicMock()
        mock_client.query.return_value = _express_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_express(ann_date="2026-01-30")

        row = result.to_dicts()[0]
        assert row["revenue"] == 117802873800.0
        assert row["n_income"] == 1355211500.0
        assert row["audit_status"] is None
        assert row["knowledge_date"] == date.today()

    def test_ticker_mode_uses_non_vip_endpoint(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = _express_response()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        adapter.fetch_earnings_express(
            source_ticker="600710.SH",
            start_date="2024-01-01",
            end_date="2026-09-30",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["api_name"] == "express"
        assert kwargs["ts_code"] == "600710.SH"
        assert kwargs["start_date"] == "20240101"

    def test_empty_response_returns_schema_frame(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame()
        adapter = FundamentalTushareAdapter(_client=mock_client)

        result = adapter.fetch_earnings_express(ann_date="2026-03-30")

        assert result.height == 0
        assert result.columns == list(EARNINGS_EXPRESS_SCHEMA)


def _forecast_response() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_code": ["000017.SZ", "000017.SZ", "000048.SZ"],
            "ann_date": ["20260130", "20260130", "20260130"],
            "end_date": ["20251231", "20251231", "20251231"],
            "type": ["预增", "预增", "预减"],
            "p_change_min": [113.71, 113.71, -82.49],
            "p_change_max": [220.57, 220.57, -76.88],
            "net_profit_min": [3600.0, 3600.0, 12500.0],
            "net_profit_max": [5400.0, 5400.0, 16500.0],
            "first_ann_date": ["20260130", "20260130", "20260130"],
            "update_flag": ["0", "1", "0"],
        }
    )


def _express_response() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_code": ["600710.SH"],
            "ann_date": ["20260130"],
            "end_date": ["20251231"],
            "revenue": [117802873800.0],
            "operate_profit": [4419237400.0],
            "total_profit": [4451363200.0],
            "n_income": [1355211500.0],
            "total_assets": [58716675400.0],
            "audit_status": [None],
        }
    )
