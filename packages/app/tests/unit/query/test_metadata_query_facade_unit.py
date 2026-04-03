"""Tests for MetadataQueryFacade — 封装 MetadataService，隐藏 SecurityQuery."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_app.query.metadata import MetadataQueryFacade


class TestMetadataQueryFacadeGetInstrument:
    """MetadataQueryFacade.get_instrument — 委托到 MetadataService."""

    def test_returns_dict_when_found(self) -> None:
        service = MagicMock(spec=["get_instrument"])
        service.get_instrument.return_value = {"instrument_id": 1, "ticker": "000001"}
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.get_instrument(1)

        assert result == {"instrument_id": 1, "ticker": "000001"}
        service.get_instrument.assert_called_once_with(1)

    def test_returns_none_when_not_found(self) -> None:
        service = MagicMock(spec=["get_instrument"])
        service.get_instrument.return_value = None
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.get_instrument(999)

        assert result is None


class TestMetadataQueryFacadeFindSecurities:
    """MetadataQueryFacade.find_securities — 内部构造 SecurityQuery 参数."""

    def test_passes_keyword_args_to_service(self) -> None:
        service = MagicMock(spec=["find_securities"])
        service.find_securities.return_value = pl.DataFrame({"instrument_id": [1]})
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.find_securities(
            asset_class="stock",
            exchange="SSE",
            is_active=True,
            source_tickers=["000001.SZ"],
        )

        assert len(result) == 1
        service.find_securities.assert_called_once_with(
            source_tickers=["000001.SZ"],
            asset_class="stock",
            exchange="SSE",
            is_active=True,
        )

    def test_default_is_active_true(self) -> None:
        service = MagicMock(spec=["find_securities"])
        service.find_securities.return_value = pl.DataFrame()
        facade = MetadataQueryFacade(metadata_service=service)

        facade.find_securities()

        service.find_securities.assert_called_once_with(
            source_tickers=None,
            asset_class=None,
            exchange=None,
            is_active=True,
        )


class TestMetadataQueryFacadeResolveInstrumentIdentifier:
    """MetadataQueryFacade.resolve_instrument_identifier — 返回 int | None."""

    def test_returns_int_when_found(self) -> None:
        service = MagicMock(spec=["resolve_instrument_identifier"])
        # Service returns InstrumentId (NewType of int)
        service.resolve_instrument_identifier.return_value = 42
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.resolve_instrument_identifier(
            ticker="000001",
            source="tushare",
        )

        assert result == 42
        assert isinstance(result, int)

    def test_returns_none_when_not_found(self) -> None:
        service = MagicMock(spec=["resolve_instrument_identifier"])
        service.resolve_instrument_identifier.return_value = None
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.resolve_instrument_identifier(
            ticker="999999",
            source="tushare",
        )

        assert result is None


class TestMetadataQueryFacadeResolveSourceTicker:
    """MetadataQueryFacade.resolve_source_ticker — 委托到 MetadataService."""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["resolve_source_ticker"])
        service.resolve_source_ticker.return_value = "000001.SZ"
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.resolve_source_ticker(
            ticker="000001",
            asset_class="stock",
            source="tushare",
        )

        assert result == "000001.SZ"
        service.resolve_source_ticker.assert_called_once_with(
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            asset_class="stock",
            source="tushare",
            asof=None,
        )


class TestMetadataQueryFacadeCalendar:
    """MetadataQueryFacade — 交易日历方法."""

    def test_is_trading_day(self) -> None:
        service = MagicMock(spec=["is_trading_day"])
        service.is_trading_day.return_value = True
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.is_trading_day("2024-01-02")

        assert result is True
        service.is_trading_day.assert_called_once_with("2024-01-02")

    def test_get_last_trading_day(self) -> None:
        service = MagicMock(spec=["get_last_trading_day"])
        service.get_last_trading_day.return_value = "2024-01-02"
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.get_last_trading_day()

        assert result == "2024-01-02"

    def test_get_last_trading_day_returns_none(self) -> None:
        service = MagicMock(spec=["get_last_trading_day"])
        service.get_last_trading_day.return_value = None
        facade = MetadataQueryFacade(metadata_service=service)

        result = facade.get_last_trading_day()

        assert result is None
