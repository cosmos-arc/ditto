"""商品复合源新浪腿测试（#436）."""

from __future__ import annotations

from typing import Protocol
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.commodity_fetcher import (
    fetch_commodity_daily,
)


class _MetalSource(Protocol):
    def fetch_metal_daily(
        self, codes: list[str], start_date: str, end_date: str
    ) -> pl.DataFrame: ...


def _metal_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [5_000_003],
            "trade_date": ["2026-10-05"],
            "trade_date_utc": [None],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [2600.0],
        }
    )


def _sina_frame(instrument_id: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [instrument_id],
            "trade_date": ["2026-10-05"],
            "trade_date_utc": [None],
            "open": [91.25],
            "high": [91.88],
            "low": [90.51],
            "close": [90.68],
        }
    )


def test_sina_leg_merges_into_commodity_batch() -> None:
    """新浪腿成功时与其他腿合并写入同一批次."""
    metal = MagicMock()
    metal.fetch_metal_daily.return_value = _metal_frame()
    sina = MagicMock()
    sina.fetch_commodities.return_value = _sina_frame(5_000_005)

    result = fetch_commodity_daily(
        "2026-10-05",
        primary_source=metal,
        fred_source=None,
        sina_source=sina,
    )

    assert result.height == 2
    sina.fetch_commodities.assert_called_once()
    kwargs = sina.fetch_commodities.call_args.kwargs
    assert kwargs["codes"] == ["CL", "GC", "SI"]
    assert kwargs["start_date"] == kwargs["end_date"] == "2026-10-05"


def test_sina_leg_failure_fails_whole_batch() -> None:
    """免费无 SLA 源故障显式报错：不得静默降级（#432 完整性合同）."""
    metal = MagicMock()
    metal.fetch_metal_daily.return_value = _metal_frame()
    sina = MagicMock()
    sina.fetch_commodities.side_effect = RuntimeError("sina down")

    with pytest.raises(RuntimeError, match="sina down"):
        fetch_commodity_daily(
            "2026-10-05",
            primary_source=metal,
            fred_source=None,
            sina_source=sina,
        )


def test_sina_leg_empty_window_is_legal_empty() -> None:
    """合法空（区间无观察行）不是失败：空帧照常合并."""
    metal = MagicMock()
    metal.fetch_metal_daily.return_value = _metal_frame()
    sina = MagicMock()
    sina.fetch_commodities.return_value = pl.DataFrame()

    result = fetch_commodity_daily(
        "2026-10-05",
        primary_source=metal,
        fred_source=None,
        sina_source=sina,
    )

    assert result.height == 1
