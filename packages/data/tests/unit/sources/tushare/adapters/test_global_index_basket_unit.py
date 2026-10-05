"""全球指数 21 指数白名单合同测试（#435）."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.models import GLOBAL_INDEX_CODES
from ditto_data.sources.tushare.adapters import index as index_adapter


def test_spec_registry_matches_official_21_code_list() -> None:
    """适配器 spec 与权威 21 码清单一一对应，无多无漏."""
    assert set(index_adapter._GLOBAL_INDEX_SPECS) == set(GLOBAL_INDEX_CODES)
    assert len(GLOBAL_INDEX_CODES) == 21


def test_ndx_is_not_registered_and_is_rejected() -> None:
    """官方表无 NDX：IXIC 是纳斯达克综合指数，不能替代纳斯达克 100."""
    assert "NDX" not in GLOBAL_INDEX_CODES
    assert "NDX" not in index_adapter._GLOBAL_INDEX_SPECS
    adapter = index_adapter.IndexTushareAdapter(_client=MagicMock())
    with pytest.raises(ValueError, match="Unsupported global index code"):
        adapter.fetch_global_daily(
            codes=["NDX"],
            start_date="2026-09-30",
            end_date="2026-09-30",
            observed_at=datetime(2026, 10, 5, tzinfo=UTC),
        )


def test_every_code_has_timezone_currency_and_close_time() -> None:
    """每个 spec 必须声明时区/计价币种/收市时刻，不留空值."""
    for code, spec in index_adapter._GLOBAL_INDEX_SPECS.items():
        assert spec.timezone, code
        assert spec.currency, code
        assert spec.close_time is not None, code


def test_every_code_fetchable_in_one_basket_call() -> None:
    """全篮子单次调用可取回：适配器逐码请求且字段符合端点合同."""
    mock_client = MagicMock()
    mock_client.query.return_value = pl.DataFrame(
        {
            "ts_code": ["SPX"],
            "trade_date": ["20260930"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "pre_close": [1.0],
            "change": [0.0],
            "pct_chg": [0.0],
            "vol": [None],
        }
    )
    adapter = index_adapter.IndexTushareAdapter(_client=mock_client)
    adapter.fetch_global_daily(
        codes=list(GLOBAL_INDEX_CODES),
        start_date="2026-09-30",
        end_date="2026-09-30",
        observed_at=datetime(2026, 10, 5, tzinfo=UTC),
    )

    requested = [call.kwargs["ts_code"] for call in mock_client.query.call_args_list]
    assert requested == list(GLOBAL_INDEX_CODES)
    # vol/amount 缺失不补真实零：amount 恒 null、vol 原样透传
    assert mock_client.query.call_args.kwargs["fields"] == (
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol"
    )
