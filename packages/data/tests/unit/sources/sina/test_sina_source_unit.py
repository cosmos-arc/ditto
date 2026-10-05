"""新浪外盘连续期货源测试（#436）."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from ditto_data.models import SINA_FOREIGN_FUTURES
from ditto_data.sources.schemas.commodity_schemas import COMMODITY_SOURCE_SCHEMA
from ditto_data.sources.sina.client import SinaClient
from ditto_data.sources.sina.source import SinaSource


def _rows() -> list[dict[str, str]]:
    return [
        {
            "date": "2026-09-30",
            "open": "91.250",
            "high": "91.880",
            "low": "90.510",
            "close": "90.680",
            "volume": "0",
            "position": "0",
            "s": "0.000",
            "settlement": "0",
        },
        {
            "date": "2026-10-01",
            "open": "90.700",
            "high": "91.000",
            "low": "90.200",
            "close": "90.900",
            "volume": "0",
            "position": "0",
            "s": "0.000",
            "settlement": "0",
        },
    ]


class TestSinaClientJsonp:
    def test_parses_jsonp_body(self) -> None:
        client = SinaClient(base_url="https://example.com")

        class _Resp:
            text = 'var _S=( [{"date":"2026-10-01","close":"1.0"}] );'

            def raise_for_status(self) -> None: ...

        client._client = MagicMock()
        client._client.get.return_value = _Resp()
        rows = client.get_global_futures_daily_kline("CL")
        assert rows == [{"date": "2026-10-01", "close": "1.0"}]

    def test_rejects_payload_without_parentheses(self) -> None:
        from ditto_data.errors.network import SourceFetchError

        client = SinaClient(base_url="https://example.com")

        class _Resp:
            text = "not jsonp"

            def raise_for_status(self) -> None: ...

        client._client = MagicMock()
        client._client.get.return_value = _Resp()
        with pytest.raises(SourceFetchError):
            client.get_global_futures_daily_kline("CL")


class TestSinaSource:
    def test_maps_real_ohlc_and_drops_placeholder_fields(self) -> None:
        """真实 OHLC 入库；占位零 volume/position/settlement 不出现在输出."""
        mock_client = MagicMock()
        mock_client.get_global_futures_daily_kline.return_value = _rows()
        source = SinaSource(client=mock_client)

        result = source.fetch_commodities(["CL"], "2026-09-30", "2026-10-01")

        assert set(result.columns) == set(COMMODITY_SOURCE_SCHEMA.schema)
        assert result.height == 2
        row = result.to_dicts()[0]
        assert row["instrument_id"] == SINA_FOREIGN_FUTURES["CL"][0]
        assert row["open"] == 91.25
        assert row["close"] == 90.68
        for placeholder in ("volume", "position", "settlement", "s"):
            assert placeholder not in result.columns

    def test_filters_to_requested_window(self) -> None:
        """端点无窗口参数：全量返回后本地过滤."""
        mock_client = MagicMock()
        mock_client.get_global_futures_daily_kline.return_value = _rows()
        source = SinaSource(client=mock_client)

        result = source.fetch_commodities(["CL"], "2026-10-01", "2026-10-01")

        assert result.height == 1
        assert str(result["trade_date"][0]) == "2026-10-01"

    def test_unknown_symbol_rejected(self) -> None:
        source = SinaSource(client=MagicMock())
        with pytest.raises(ValueError, match="not registered"):
            source.fetch_commodities(["ZSD"], "2026-01-01", "2026-01-31")

    def test_empty_window_returns_schema_frame(self) -> None:
        mock_client = MagicMock()
        mock_client.get_global_futures_daily_kline.return_value = _rows()
        source = SinaSource(client=mock_client)

        result = source.fetch_commodities(["GC"], "2026-11-01", "2026-11-02")

        assert result.height == 0
        assert set(result.columns) == set(COMMODITY_SOURCE_SCHEMA.schema)


class TestSinaWhitelist:
    VALUES: ClassVar[dict[str, tuple[int, str, str, str]]] = SINA_FOREIGN_FUTURES

    def test_identity_units_registered_per_ticker(self) -> None:
        """逐品种登记 instrument_id/单位/币种；身份未核实的 ZSD 不在表."""
        assert set(self.VALUES) == {"CL", "GC", "SI"}
        assert "ZSD" not in self.VALUES
        ids = [spec[0] for spec in self.VALUES.values()]
        assert len(set(ids)) == 3
        for _iid, unit, currency, _desc in self.VALUES.values():
            assert unit
            assert currency == "USD"

    def test_instrument_ids_in_commodity_range(self) -> None:
        for iid in (spec[0] for spec in self.VALUES.values()):
            assert 5_000_000 <= iid <= 5_999_999
