"""fuyao 冗余源单测 — client 信封 fail-closed 与帧转换."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import polars as pl
import pytest
import respx
from ditto_data.sources.base import SourceConfigurationError, SourceFetchError
from ditto_data.sources.fuyao.client import (
    FuyaoClient,
    date_to_ms,
    ms_to_date,
)
from ditto_data.sources.fuyao.source import FuyaoSource, _to_thscode

_BASE = "https://fuyao.aicubes.cn"


def _client() -> FuyaoClient:
    return FuyaoClient(base_url=_BASE, api_key="not_a_secret")


@pytest.mark.unit
class TestFuyaoTimeConversions:
    """北京时区毫秒戳换算."""

    def test_roundtrip(self) -> None:
        assert ms_to_date(date_to_ms(date(2025, 8, 18))) == date(2025, 8, 18)

    def test_known_dump_value(self) -> None:
        # 冒烟实测：600519.SH 2025-08-18 的 date_ms
        assert ms_to_date(1755446400000) == date(2025, 8, 18)

    def test_ticker_suffix(self) -> None:
        assert _to_thscode("600519") == "600519.SH"
        assert _to_thscode("000001") == "000001.SZ"
        assert _to_thscode("300750") == "300750.SZ"
        assert _to_thscode("510300") == "510300.SH"
        assert _to_thscode("830799") == "830799.BJ"
        assert _to_thscode("600519.SH") == "600519.SH"


@pytest.mark.unit
class TestFuyaoClientEnvelope:
    """信封校验 fail-closed."""

    def test_missing_api_key_is_configuration_error(self) -> None:
        with pytest.raises(SourceConfigurationError):
            FuyaoClient(api_key="")

    @respx.mock
    def test_success_returns_data(self) -> None:
        respx_mock = respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 0, "message": "success", "data": {"item": []}}
            )
        )
        assert _client().get("/api/x") == {"item": []}
        assert respx_mock.called

    @respx.mock
    def test_business_error_raises(self) -> None:
        respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(
                200, json={"code": 2001, "message": "invalid key", "data": None}
            )
        )
        with pytest.raises(SourceFetchError, match="code=2001"):
            _client().get("/api/x")

    @respx.mock
    def test_missing_data_payload_raises(self) -> None:
        respx.get(f"{_BASE}/api/x").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "ok"})
        )
        with pytest.raises(SourceFetchError, match="no data payload"):
            _client().get("/api/x")


def _historical_items() -> list[dict[str, object]]:
    return [
        {
            "date_ms": date_to_ms(date(2025, 8, 18)),
            "open_price": 10.0,
            "high_price": 11.0,
            "low_price": 9.5,
            "close_price": 10.5,
            "volume": 100.0,
            "turnover": 1050.0,
        },
        {
            "date_ms": date_to_ms(date(2025, 8, 19)),
            "open_price": 10.5,
            "high_price": 11.5,
            "low_price": 10.0,
            "close_price": 11.0,
            "volume": 200.0,
            "turnover": 2200.0,
        },
    ]


@pytest.mark.unit
class TestFuyaoSourceBars:
    """原始日线帧转换与两模式校验."""

    def _source_with_items(self, items: list[dict[str, object]]) -> FuyaoSource:
        client = MagicMock()
        client.get.return_value = {"item": items}
        return FuyaoSource(client=client)

    def test_ticker_mode_builds_source_schema_frame(self) -> None:
        source = self._source_with_items(_historical_items())

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2025-08-18", end_date="2025-08-19"
        )

        assert frame["source_ticker"].unique().to_list() == ["600519.SH"]
        assert frame["trade_date"].to_list() == [date(2025, 8, 18), date(2025, 8, 19)]
        assert frame["pre_close"].to_list() == [None, 10.5]
        assert frame["knowledge_date"].to_list() == [
            date(2025, 8, 19),
            date(2025, 8, 20),
        ]
        assert frame["pct_change"][1] == pytest.approx(4.761904, abs=1e-4)
        # 原始价：REST 请求显式 adjust=none
        kwargs = source._client.get.call_args.kwargs
        assert kwargs["params"]["adjust"] == "none"
        assert kwargs["params"]["thscode"] == "600519.SH"

    def test_ticker_mode_empty_items_returns_typed_empty_frame(self) -> None:
        source = self._source_with_items([])

        frame = source.fetch_stock_daily(
            source_ticker="600519", start_date="2025-08-18", end_date="2025-08-18"
        )

        assert frame.is_empty()
        assert "knowledge_date" in frame.columns

    def test_mode_validation(self) -> None:
        source = self._source_with_items([])
        with pytest.raises(ValueError, match="互斥"):
            source.fetch_stock_daily(trade_date="2025-08-18", source_ticker="600519.SH")
        with pytest.raises(ValueError, match="必须指定"):
            source.fetch_stock_daily()
        with pytest.raises(ValueError, match="start_date 和 end_date"):
            source.fetch_stock_daily(source_ticker="600519.SH")

    def test_reconciliation_frame_uses_bare_ticker(self) -> None:
        source = self._source_with_items(_historical_items())

        frame = source.fetch_stock_daily_bars(["600519"], "2025-08-19")

        assert frame.columns == [
            "ticker",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]
        assert frame["ticker"].to_list() == ["600519"]
        assert frame["trade_date"].to_list() == [date(2025, 8, 19)]
        assert frame["close"].to_list() == [11.0]
        # 单位归一：股→手(÷100)、元→千元(÷1000)
        assert frame["volume"].to_list() == [200.0 / 100]
        assert frame["amount"].to_list() == [2200.0 / 1000]

    def test_market_mode_filters_dump_to_target_date(self, tmp_path: Path) -> None:
        raw = pl.DataFrame(
            {
                "thscode": ["600519.SH", "600519.SH", "000001.SZ"],
                "currency": ["CNY"] * 3,
                "interval": ["1d"] * 3,
                "adjusted": ["none"] * 3,
                "date_ms": [
                    date_to_ms(date(2025, 8, 18)),
                    date_to_ms(date(2025, 8, 19)),
                    date_to_ms(date(2025, 8, 19)),
                ],
                "open_price": [10.0, 10.5, 12.0],
                "high_price": [11.0, 11.5, 13.0],
                "low_price": [9.5, 10.0, 11.5],
                "close_price": [10.5, 11.0, 12.5],
                "volume": [100.0, 200.0, 300.0],
                "turnover": [1050.0, 2200.0, 3750.0],
            }
        )
        dump = tmp_path / "daily-k-10d.parquet"
        raw.write_parquet(dump)

        source = FuyaoSource(client=MagicMock())
        downloaded: list[Path] = []

        def fake_download(kind: str, dest: Path) -> Path:
            downloaded.append(dest)
            raw.write_parquet(dest)
            return dest

        source.download_market_dump = fake_download  # type: ignore[method-assign]

        frame = source.fetch_stock_daily("2025-08-19")

        assert downloaded[0].suffix == ".parquet"
        assert sorted(frame["source_ticker"].to_list()) == [
            "000001.SZ",
            "600519.SH",
        ]
        # dump 窗口内推导 pre_close
        assert frame.filter(pl.col("source_ticker") == "600519.SH")[
            "pre_close"
        ].to_list() == [10.5]
        assert frame.filter(pl.col("source_ticker") == "000001.SZ")[
            "pre_close"
        ].to_list() == [None]
