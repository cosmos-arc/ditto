"""#627 前十股东两榜分发器单测——日更市场级 ann_date / 按标的区间披露锚裁剪."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare._utils import to_compact_date
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_data.sources.tushare.fundamental_source import (
    fetch_top10_floatholders,
    fetch_top10_holders,
)


def _holders_frame(knowledge: date, report: date) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": ["600000.SH"],
            "report_date": [report],
            "knowledge_date": [knowledge],
            "holder_name": ["上海国际集团有限公司"],
            "hold_amount": [3.1575e9],
            "hold_ratio": [16.9272],
            "hold_float_ratio": [21.159],
            "hold_change": [0.0],
            "holder_type": ["一般企业"],
        }
    )


@pytest.mark.unit
class TestTop10HoldersDispatch:
    """日更（公告日市场级）与按标的回填（报告期区间）两模式."""

    def test_trade_date_queries_market_wide_announcement_date(self) -> None:
        capital = MagicMock(spec=CapitalTushareAdapter)
        capital.fetch_top10_holders.return_value = _holders_frame(
            date(2026, 3, 20), date(2025, 12, 31)
        )

        result = fetch_top10_holders(capital, trade_date="2026-03-20")

        capital.fetch_top10_holders.assert_called_once_with(ann_date="20260320")
        assert result.height == 1

    def test_instrument_mode_uses_period_range_and_filters_knowledge_window(
        self,
    ) -> None:
        capital = MagicMock(spec=CapitalTushareAdapter)
        # 区间内披露行保留；区间外晚披露行剔除（PIT：不进本 chunk）
        capital.fetch_top10_holders.return_value = pl.concat(
            [
                _holders_frame(date(2014, 3, 20), date(2013, 12, 31)),
                _holders_frame(date(2015, 3, 30), date(2014, 12, 31)),
            ]
        )

        result = fetch_top10_holders(
            capital,
            source_ticker="600000.SH",
            start_date="2014-01-01",
            end_date="2014-12-31",
        )

        capital.fetch_top10_holders.assert_called_once_with(
            ts_code="600000.SH",
            start_date="20140101",
            end_date="20141231",
        )
        assert result.height == 1
        assert result.row(0, named=True)["knowledge_date"] == date(2014, 3, 20)

    def test_requires_mode_arguments(self) -> None:
        capital = MagicMock(spec=CapitalTushareAdapter)
        with pytest.raises(ValueError, match="source_ticker"):
            fetch_top10_holders(capital)
        with pytest.raises(ValueError, match="start_date and end_date"):
            fetch_top10_holders(capital, source_ticker="600000.SH")

    def test_floatholders_shapes_mirror_holders(self) -> None:
        capital = MagicMock(spec=CapitalTushareAdapter)
        capital.fetch_top10_floatholders.return_value = _holders_frame(
            date(2014, 3, 20), date(2013, 12, 31)
        )

        result = fetch_top10_floatholders(
            capital,
            source_ticker="600000.SH",
            start_date="2014-01-01",
            end_date="2014-12-31",
        )

        capital.fetch_top10_floatholders.assert_called_once_with(
            ts_code="600000.SH",
            start_date="20140101",
            end_date="20141231",
        )
        assert result.height == 1


@pytest.mark.unit
class TestCompactDateReuse:
    """分发器沿用 to_compact_date 归一（与 fund_portfolio 同语义）."""

    def test_compact_conversion(self) -> None:
        assert to_compact_date("2014-01-01") == "20140101"
