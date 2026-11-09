"""Dividend range requests must filter announcement dates locally."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.capital_market import (
    CapitalMarketTushareAdapter,
)
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter


@pytest.mark.pit
@pytest.mark.parametrize(
    "adapter_class", [CapitalMarketTushareAdapter, FundamentalTushareAdapter]
)
def test_dividend_range_excludes_future_announcement(adapter_class):
    client = MagicMock()
    client.query.return_value = pl.DataFrame(
        {
            "ts_code": ["600519.SH"] * 2,
            "ann_date": ["20260601", "20260602"],
            "ex_date": ["20260630"] * 2,
            "record_date": ["20260629"] * 2,
            "cash_div": [1.0, 999.0],
            "cash_div_tax": [1.25, 999.0],
            "pay_date": ["20260702"] * 2,
            "imp_ann_date": ["20260620"] * 2,
            "end_date": ["20251231"] * 2,
            "stk_div": [0.0] * 2,
            "stk_bo_rate": [0.0] * 2,
            "stk_co_rate": [0.0] * 2,
            "div_listdate": [None] * 2,
            "div_proc": ["实施"] * 2,
        }
    )
    frame = adapter_class(_client=client).fetch_dividend(
        ts_code="600519.SH", start_date="20260601", end_date="20260601"
    )
    assert frame["dividend_per_share"].to_list() == [1.0]
    assert frame["knowledge_date"].to_list() == [date(2026, 6, 1)]
    assert frame["ex_dividend_date"].to_list() == [date(2026, 6, 30)]
    assert frame["gross_dividend_per_share"].to_list() == [1.25]
    assert frame["record_date"].to_list() == [date(2026, 6, 29)]
    assert frame["pay_date"].to_list() == [date(2026, 7, 2)]
    assert frame["implementation_date"].to_list() == [date(2026, 6, 20)]
    assert frame["stock_dividend_ratio"].to_list() == [0.0]
    assert {"cash_div_tax", "pay_date", "imp_ann_date", "stk_div"} <= set(
        client.query.call_args.kwargs["fields"].split(",")
    )
    assert "start_date" not in client.query.call_args.kwargs
    assert "end_date" not in client.query.call_args.kwargs
