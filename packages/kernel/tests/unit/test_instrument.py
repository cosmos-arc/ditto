"""Instrument 子域单元测试."""

import pytest
from ditto_kernel.instrument import AssetClass, Exchange, InstrumentIngestParams


class TestAssetClass:
    """AssetClass 枚举测试."""

    def test_all_values(self) -> None:
        expected = {"stock", "etf", "index", "future", "bond", "fund"}
        assert {e.value for e in AssetClass} == expected

    def test_value_access(self) -> None:
        assert AssetClass.STOCK.value == "stock"
        assert AssetClass.ETF.value == "etf"


class TestExchange:
    """Exchange 枚举测试."""

    def test_all_values(self) -> None:
        expected = {"XSHE", "XSHG", "XBSE"}
        assert {e.value for e in Exchange} == expected

    def test_shanghai(self) -> None:
        assert Exchange.XSHG.value == "XSHG"

    def test_shenzhen(self) -> None:
        assert Exchange.XSHE.value == "XSHE"


class TestInstrumentIngestParams:
    """InstrumentIngestParams 测试."""

    def test_frozen(self) -> None:
        params = InstrumentIngestParams(instrument_id=1)
        with pytest.raises(AttributeError):
            params.instrument_id = 2

    def test_has_identifier_with_instrument_id(self) -> None:
        params = InstrumentIngestParams(instrument_id=1)
        assert params.has_identifier is True

    def test_has_identifier_with_standard_ticker(self) -> None:
        params = InstrumentIngestParams(standard_ticker="510300.SH")
        assert params.has_identifier is True

    def test_has_identifier_with_ticker(self) -> None:
        params = InstrumentIngestParams(ticker="510300")
        assert params.has_identifier is True

    def test_has_no_identifier(self) -> None:
        params = InstrumentIngestParams()
        assert params.has_identifier is False

    def test_primary_identifier_instrument_id_priority(self) -> None:
        params = InstrumentIngestParams(instrument_id=1, standard_ticker="510300.SH")
        assert params.primary_identifier == "1"

    def test_primary_identifier_standard_ticker(self) -> None:
        params = InstrumentIngestParams(standard_ticker="510300.SH")
        assert params.primary_identifier == "510300.SH"

    def test_primary_identifier_ticker(self) -> None:
        params = InstrumentIngestParams(ticker="510300")
        assert params.primary_identifier == "510300"

    def test_primary_identifier_none(self) -> None:
        params = InstrumentIngestParams()
        assert params.primary_identifier is None

    def test_default_dates(self) -> None:
        params = InstrumentIngestParams(instrument_id=1)
        assert params.start_date == ""
        assert params.end_date == ""

    def test_custom_dates(self) -> None:
        params = InstrumentIngestParams(
            instrument_id=1, start_date="2024-01-01", end_date="2024-12-31"
        )
        assert params.start_date == "2024-01-01"
        assert params.end_date == "2024-12-31"
