"""Tests for _commodity_fetcher — FRED/Tushare 双源商品数据获取."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from ditto_app.process.ingestion.commodity_fetcher import fetch_commodity_daily

_UNSET: object = object()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fred_df() -> pl.DataFrame:
    """构造模拟 FRED 返回的 DataFrame（原油/VIX）."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": ["2024-01-01", "2024-01-01"],
            "close": [100.0, 25.0],
        }
    )


def _make_metal_df() -> pl.DataFrame:
    """构造模拟 Tushare 返回的 DataFrame（贵金属）."""
    return pl.DataFrame(
        {
            "instrument_id": [3, 4],
            "trade_date": ["2024-01-01", "2024-01-01"],
            "close": [2000.0, 25.0],
        }
    )


def _make_sources(
    *,
    fred_df: pl.DataFrame | Exception | None | object = _UNSET,
    metal_df: pl.DataFrame | Exception | None | object = _UNSET,
) -> tuple[MagicMock, MagicMock | None]:
    """构造 mock 数据源.

    Args:
        fred_df: FRED 返回值。传入 Exception 模拟异常，None 表示不创建 fred_source。
        metal_df: Tushare 返回值。传入 Exception 模拟异常。

    Returns:
        (primary_source, fred_source) 元组。
    """
    primary_source = MagicMock()

    _metal: pl.DataFrame | Exception = cast(
        "pl.DataFrame | Exception",
        _make_metal_df() if metal_df is _UNSET else metal_df,
    )
    if isinstance(_metal, Exception):
        primary_source.fetch_metal_daily.side_effect = _metal
    else:
        primary_source.fetch_metal_daily.return_value = _metal

    if fred_df is None:
        return primary_source, None

    fred_source = MagicMock()
    _fred: pl.DataFrame | Exception = cast(
        "pl.DataFrame | Exception",
        _make_fred_df() if fred_df is _UNSET else fred_df,
    )
    if isinstance(_fred, Exception):
        fred_source.fetch_commodities.side_effect = _fred
    else:
        fred_source.fetch_commodities.return_value = _fred

    return primary_source, fred_source


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchCommodityDaily:
    """fetch_commodity_daily 双源获取逻辑测试."""

    @pytest.fixture(autouse=True)
    def _patch_code_mappings(self):  # type: ignore[misc]
        """提取重复的 @patch 装饰器为 autouse fixture."""
        with (
            patch(
                "ditto_app.process.ingestion.commodity_fetcher.METAL_CODE_ALIASES",
                {
                    "COMMOD_GOLD": "XAUUSD.FXCM",
                    "COMMOD_SILVER": "XAGUSD.FXCM",
                },
            ),
            patch(
                "ditto_app.process.ingestion.commodity_fetcher.VIX_CODE_TO_INSTRUMENT_ID",
                {
                    "VIX_30D": 5_100_001,
                },
            ),
        ):
            yield

    def test_normal_dual_source_merge(
        self,
    ) -> None:
        """FRED 和 Tushare 都返回数据，合并结果包含两源行数."""
        primary, fred = _make_sources()

        result = fetch_commodity_daily(
            "2024-01-01",
            primary_source=primary,
            fred_source=fred,
        )

        assert not result.is_empty()
        assert len(result) == 4  # 2 from FRED + 2 from metal

        # 验证调用参数
        assert fred is not None
        fred.fetch_commodities.assert_called_once_with(
            codes=["COMMOD_WTI", "COMMOD_BRENT", "VIX_30D"],
            start_date="2024-01-01",
            end_date="2024-01-01",
        )
        primary.fetch_metal_daily.assert_called_once_with(
            codes=["XAUUSD.FXCM", "XAGUSD.FXCM"],
            start_date="2024-01-01",
            end_date="2024-01-01",
        )

    def test_fred_failure_degrades_to_tushare_only(
        self,
    ) -> None:
        """FRED 抛异常，仅返回 Tushare 数据."""
        primary, fred = _make_sources(
            fred_df=RuntimeError("FRED API timeout"),
        )

        result = fetch_commodity_daily(
            "2024-01-01",
            primary_source=primary,
            fred_source=fred,
        )

        assert not result.is_empty()
        assert len(result) == 2
        assert result["instrument_id"].to_list() == [3, 4]

    def test_tushare_failure_degrades_to_fred_only(
        self,
    ) -> None:
        """Tushare 抛异常，仅返回 FRED 数据."""
        primary, fred = _make_sources(
            metal_df=RuntimeError("Tushare rate limit"),
        )

        result = fetch_commodity_daily(
            "2024-01-01",
            primary_source=primary,
            fred_source=fred,
        )

        assert not result.is_empty()
        assert len(result) == 2
        assert result["instrument_id"].to_list() == [1, 2]

    def test_both_sources_fail_returns_empty(
        self,
    ) -> None:
        """FRED 和 Tushare 都抛异常，返回空 DataFrame."""
        primary, fred = _make_sources(
            fred_df=RuntimeError("FRED down"),
            metal_df=RuntimeError("Tushare down"),
        )

        result = fetch_commodity_daily(
            "2024-01-01",
            primary_source=primary,
            fred_source=fred,
        )

        assert result.is_empty()
        assert len(result) == 0

    def test_fred_not_configured(
        self,
    ) -> None:
        """fred_source=None，仅返回 Tushare 数据."""
        primary, fred = _make_sources(fred_df=None)

        assert fred is None

        result = fetch_commodity_daily(
            "2024-01-01",
            primary_source=primary,
            fred_source=fred,
        )

        assert not result.is_empty()
        assert len(result) == 2
        assert result["instrument_id"].to_list() == [3, 4]
