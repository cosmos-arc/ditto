"""#521/#522 fina_indicator 披露增量 + fund_portfolio 双模式单测."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare._fundamental import (
    fetch_fina_indicator,
    fetch_fund_portfolio,
    max_quarters_in_range,
)
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter


def _compact(value: str) -> str:
    return value.replace("-", "")


@pytest.mark.unit
class TestFinaIndicatorDisclosureDelta:
    """fina_indicator 复用三表披露增量语义：近期报告期超集 + kd 截止过滤."""

    def test_trade_date_pulls_recent_periods_and_filters_future_knowledge(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        # 两期响应：Q2 披露日早于截止日保留；Q3 披露日晚于截止日剔除
        # adapter 输出契约：ts_code→source_ticker、ann_date→knowledge_date、
        # end_date→report_date（指标列透传）
        fundamental.fetch_fina_indicator.side_effect = [
            pl.DataFrame(
                {
                    "source_ticker": ["600519.SH"],
                    "knowledge_date": [date(2026, 7, 21)],
                    "report_date": [date(2026, 6, 30)],
                    "eps": [33.19],
                    "roe": [19.2],
                }
            ),
            pl.DataFrame(
                {
                    "source_ticker": ["600519.SH"],
                    "knowledge_date": [date(2026, 10, 28)],
                    "report_date": [date(2026, 9, 30)],
                    "eps": [45.0],
                    "roe": [21.0],
                }
            ),
        ] + [
            pl.DataFrame(
                schema={
                    "source_ticker": pl.String,
                    "knowledge_date": pl.Date,
                    "report_date": pl.Date,
                }
            )
        ] * 6

        result = fetch_fina_indicator(fundamental, _compact, trade_date="2026-09-30")

        assert result.height == 1
        row = result.row(0, named=True)
        assert row["knowledge_date"] == date(2026, 7, 21)
        assert row["report_date"] == date(2026, 6, 30)
        # 指标列透传：未在 mapping 声明的列原样带出
        assert row["eps"] == pytest.approx(33.19)

    def test_instrument_mode_uses_ann_window(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fina_indicator.return_value = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "knowledge_date": [date(2026, 4, 27)],
                "report_date": [date(2024, 3, 31)],
                "eps": [19.16],
            }
        )
        result = fetch_fina_indicator(
            fundamental,
            _compact,
            source_ticker="600519.SH",
            start_date="2026-01-01",
            end_date="2026-06-30",
        )
        call = fundamental.fetch_fina_indicator.call_args.kwargs
        assert call["ts_code"] == "600519.SH"
        assert call["start_date"] == "20260101"
        assert call["end_date"] == "20260630"
        assert result.height == 1


@pytest.mark.unit
class TestFundPortfolioModes:
    """fund_portfolio 公告日驱动（日更）/报告期窗口（按基金回填）."""

    def test_trade_date_queries_exact_announcement_date(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        # adapter 输出契约：ann_date→knowledge_date、end_date→report_date、
        # symbol→holding_symbol、mkv→market_value、amount→holding_shares
        fundamental.fetch_fund_portfolio.return_value = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "000001.OF"],
                "report_date": [date(2026, 6, 30), date(2026, 6, 30)],
                "knowledge_date": [date(2026, 7, 21), date(2026, 7, 21)],
                "holding_symbol": ["300308.SZ", "002371.SZ"],
                "market_value": [4504019440.0, 145269519.68],
                "holding_shares": [3546472.0, 164228.0],
                "stk_mkv_ratio": [4.95, 4.61],
                "stk_float_ratio": [0.32, 0.02],
            }
        )
        result = fetch_fund_portfolio(fundamental, _compact, trade_date="2026-07-21")

        fundamental.fetch_fund_portfolio.assert_called_once_with(ann_date="20260721")
        assert result.height == 2
        row = result.row(0, named=True)
        assert row["holding_symbol"] == "300308.SZ"
        assert row["market_value"] == pytest.approx(4504019440.0)
        assert row["holding_shares"] == pytest.approx(3546472.0)

    def test_instrument_mode_loops_quarters_and_filters_late_disclosure(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fund_portfolio.side_effect = [
            pl.DataFrame(
                {
                    "source_ticker": ["510300.SH"],
                    "report_date": [date(2026, 3, 31)],
                    "knowledge_date": [date(2026, 4, 22)],
                    "holding_symbol": ["600519.SH"],
                    "market_value": [1.0],
                    "holding_shares": [2.0],
                    "stk_mkv_ratio": [0.1],
                    "stk_float_ratio": [0.01],
                }
            ),
            pl.DataFrame(
                {
                    "source_ticker": ["510300.SH"],
                    "report_date": [date(2026, 6, 30)],
                    "knowledge_date": [date(2026, 7, 21)],
                    "holding_symbol": ["600519.SH"],
                    "market_value": [1.5],
                    "holding_shares": [2.5],
                    "stk_mkv_ratio": [0.2],
                    "stk_float_ratio": [0.02],
                }
            ),
        ]
        result = fetch_fund_portfolio(
            fundamental,
            _compact,
            source_ticker="510300.SH",
            start_date="2026-04-01",
            end_date="2026-05-31",
        )

        periods = [
            call.kwargs["period"]
            for call in fundamental.fetch_fund_portfolio.call_args_list
        ]
        # 区间窗口按季度数+1 覆盖边界季度；每期都带 ts_code
        assert len(periods) == max_quarters_in_range("2026-04-01", "2026-05-31")
        assert all(
            call.kwargs["ts_code"] == "510300.SH"
            for call in fundamental.fetch_fund_portfolio.call_args_list
        )
        # 披露晚于 end_date 的 Q2 行被剔除，只剩 Q1
        assert result.height == 1
        assert result.row(0, named=True)["report_date"] == date(2026, 3, 31)

    def test_requires_mode_arguments(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        with pytest.raises(ValueError, match="source_ticker"):
            fetch_fund_portfolio(fundamental, _compact)
        with pytest.raises(ValueError, match="start_date and end_date"):
            fetch_fund_portfolio(fundamental, _compact, source_ticker="510300.SH")


@pytest.mark.unit
class TestFinaIndicatorDedupDeterminism:
    """#521 验收「多版本去重有测试锁定」：确定性 keep-one + 数值归一."""

    def _duplicate_rows(self) -> pl.DataFrame:
        base = {
            "source_ticker": ["600519.SH", "600519.SH"],
            "report_date": [date(2026, 6, 30), date(2026, 6, 30)],
            "knowledge_date": [date(2026, 7, 21), date(2026, 7, 21)],
            "eps": [33.19, 33.20],
            "roe": [19.2, 19.3],
        }
        return pl.DataFrame(base)

    def test_same_rows_both_orders_yield_identical_output(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )

        forward = _dedupe_fina_disclosure_key(self._duplicate_rows())
        reversed_ = _dedupe_fina_disclosure_key(self._duplicate_rows().reverse())
        assert forward.height == 1
        assert reversed_.height == 1
        assert forward.equals(reversed_)

    def test_numeric_passthrough_columns_normalized_to_float(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _normalize_fina_numeric_columns,
        )

        frame = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "report_date": [date(2026, 6, 30)],
                "knowledge_date": [date(2026, 7, 21)],
                "eps": [33],
                "roe": [19.2],
            }
        )
        normalized = _normalize_fina_numeric_columns(frame)
        assert normalized["eps"].dtype == pl.Float64
        assert normalized["roe"].dtype == pl.Float64
        assert normalized["source_ticker"].dtype == pl.String

    def test_vip_fetch_dedupes_same_disclosure_key(self) -> None:
        from unittest.mock import MagicMock

        from ditto_data.sources.tushare.adapters.fundamental import (
            FundamentalTushareAdapter,
        )

        client = MagicMock()
        # client 返回原始列形状（transform 前端）：ts_code/ann_date/end_date
        client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["600519.SH", "600519.SH"],
                "ann_date": ["20260721", "20260721"],
                "end_date": ["20260630", "20260630"],
                "eps": [33.19, 33.20],
                "roe": [19.2, 19.3],
            }
        )
        adapter = FundamentalTushareAdapter(_client=client)

        frame = adapter.fetch_fina_indicator_vip(period="20260630")

        assert frame.height == 1
        assert frame["eps"].dtype == pl.Float64
