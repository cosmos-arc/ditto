"""Tests for macro endpoint window-parameter contracts（#434 月度参数接线）."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_data.sources.tushare.processors.mappings.macro import (
    TushareMacroIndicator,
)


def _indicator(
    api_name: str,
    field: str,
    frequency: str,
    range_params: tuple[str, str],
) -> TushareMacroIndicator:
    return TushareMacroIndicator(
        api_name=api_name,
        code=f"TEST_{field.upper()}",
        field=field,
        name=field,
        category="economic",
        frequency=frequency,  # type: ignore[arg-type]
        unit="%",
        description="test",
        range_params=range_params,
    )


@pytest.mark.unit
class TestMacroWindowParams:
    def test_monthly_endpoints_send_start_m_end_m(self) -> None:
        """cn_cpi 等月度端点发 YYYYMM 窗口，不再发 start_date."""
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {"month": ["202501", "202502"], "nt_yoy": [0.5, -0.2]}
        )
        adapter = MacroTushareAdapter(_client=mock_client)

        adapter.fetch_indicators(
            codes=["CN_CPI_YOY"],
            start_date="2025-01-01",
            end_date="2025-02-28",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["start_m"] == "202501"
        assert kwargs["end_m"] == "202502"
        assert "start_date" not in kwargs

    def test_quarterly_gdp_sends_start_q_end_q(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {"quarter": ["2025Q1"], "gdp_yoy": [5.4]}
        )
        adapter = MacroTushareAdapter(_client=mock_client)

        adapter.fetch_indicators(
            codes=["CN_GDP_YOY"],
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["start_q"] == "2025Q1"
        assert kwargs["end_q"] == "2025Q1"

    def test_daily_shibor_keeps_start_date_end_date(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame({"date": [], "on": []})
        adapter = MacroTushareAdapter(_client=mock_client)

        adapter.fetch_indicators(
            codes=["CN_SHIBOR_ON"],
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["start_date"] == "20250101"
        assert kwargs["end_date"] == "20250131"

    def test_sf_month_registers_distinct_units_per_field(self) -> None:
        """社融增量亿元、存量万亿元，字段级单位在注册表区分。"""
        from ditto_data.sources.tushare.processors.mappings.macro import (
            TUSHARE_MACRO_INDICATORS,
        )

        assert TUSHARE_MACRO_INDICATORS["CN_SF_FLOW_MONTH"].unit == "亿元"
        assert TUSHARE_MACRO_INDICATORS["CN_SF_FLOW_CUM"].unit == "亿元"
        assert TUSHARE_MACRO_INDICATORS["CN_SF_STOCK"].unit == "万亿元"
        for code in ("CN_SF_FLOW_MONTH", "CN_SF_FLOW_CUM", "CN_SF_STOCK"):
            assert TUSHARE_MACRO_INDICATORS[code].api_name == "sf_month"
            assert TUSHARE_MACRO_INDICATORS[code].range_params == ("start_m", "end_m")

    def test_sf_month_fetch_passes_through_schema(self) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "month": ["202508", "202507"],
                "inc_month": [25660.0, 11307.0],
                "inc_cumval": [265555.0, 239895.0],
                "stk_endval": [433.65, 431.25],
            }
        )
        adapter = MacroTushareAdapter(_client=mock_client)

        result = adapter.fetch_indicators(
            codes=["CN_SF_FLOW_MONTH", "CN_SF_FLOW_CUM", "CN_SF_STOCK"],
            start_date="2025-07-01",
            end_date="2025-08-31",
        )

        kwargs = mock_client.query.call_args.kwargs
        assert kwargs["api_name"] == "sf_month"
        assert kwargs["start_m"] == "202507"
        assert kwargs["end_m"] == "202508"
        units = {row["indicator_code"]: row["unit"] for row in result.to_dicts()}
        assert units["CN_SF_FLOW_MONTH"] == "亿元"
        assert units["CN_SF_STOCK"] == "万亿元"
        assert result.height == 6  # 2 个月 × 3 指标

    def test_mixed_range_contracts_within_one_api_rejected(self) -> None:
        adapter = MacroTushareAdapter(_client=MagicMock())
        mixed = [
            _indicator("cn_test", "a", "monthly", ("start_m", "end_m")),
            _indicator("cn_test", "b", "daily", ("start_date", "end_date")),
        ]
        with pytest.raises(ValueError, match="window contract"):
            adapter._resolve_range_params(mixed)
