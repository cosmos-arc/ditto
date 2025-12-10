"""Unit tests for ETF data contracts."""

from datetime import date

import pytest
from ditto_foundation.contracts.etf import ETFInfoModel


class TestETFInfoModel:
    """Test cases for ETFInfoModel."""

    def test_valid_etf_info(self) -> None:
        """Test creating model with valid data."""
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "fund_manager": "华夏基金",
            "tracking_index": "沪深300指数",
            "establishment_date": date(2012, 5, 4),
        }
        etf = ETFInfoModel(**data)

        assert etf.symbol == "510300"
        assert etf.name == "沪深300ETF"
        assert etf.fund_manager == "华夏基金"
        assert etf.tracking_index == "沪深300指数"
        assert etf.establishment_date == date(2012, 5, 4)

    def test_valid_etf_info_minimal(self) -> None:
        """Test creating model with minimal required data."""
        etf = ETFInfoModel(symbol="159919", name="沪深300ETF")

        assert etf.symbol == "159919"
        assert etf.name == "沪深300ETF"
        assert etf.fund_manager is None
        assert etf.tracking_index is None
        assert etf.establishment_date is None

    def test_symbol_validation_uppercase(self) -> None:
        """Test that symbol is converted to uppercase."""
        etf = ETFInfoModel(symbol="510300", name="Test ETF")
        assert etf.symbol == "510300"  # Already numeric, no change

        etf = ETFInfoModel(symbol="510300", name="Test ETF")
        assert etf.symbol == "510300"

    def test_symbol_validation_too_short(self) -> None:
        """Test that short symbols raise validation error."""
        with pytest.raises(
            ValueError, match="ETF symbol must be at least 6 characters"
        ):
            ETFInfoModel(symbol="12345", name="Test ETF")

    def test_symbol_validation_empty(self) -> None:
        """Test that empty symbols raise validation error."""
        with pytest.raises(
            ValueError, match="ETF symbol must be at least 6 characters"
        ):
            ETFInfoModel(symbol="", name="Test ETF")

    def test_name_validation_stripping(self) -> None:
        """Test that name is stripped of whitespace."""
        etf = ETFInfoModel(symbol="510300", name="  Test ETF  ")
        assert etf.name == "Test ETF"

    def test_name_validation_too_short(self) -> None:
        """Test that short names raise validation error."""
        with pytest.raises(ValueError, match="ETF name must be at least 2 characters"):
            ETFInfoModel(symbol="510300", name="  ")

    def test_name_validation_empty(self) -> None:
        """Test that empty names raise validation error."""
        with pytest.raises(ValueError, match="ETF name must be at least 2 characters"):
            ETFInfoModel(symbol="510300", name="")

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields raise validation error."""
        with pytest.raises(ValueError):
            ETFInfoModel(symbol="510300", name="Test ETF", extra_field="not allowed")

    def test_model_serialization(self) -> None:
        """Test model serialization to dict."""
        data = {
            "symbol": "510300",
            "name": "沪深300ETF",
            "fund_manager": None,
            "tracking_index": None,
            "establishment_date": None,
        }
        etf = ETFInfoModel(symbol="510300", name="沪深300ETF")

        assert etf.model_dump() == data

    def test_model_json_serialization(self) -> None:
        """Test model JSON serialization."""
        etf = ETFInfoModel(symbol="510300", name="沪深300ETF")
        json_str = etf.model_dump_json()

        assert '"symbol":"510300"' in json_str
        assert '"name":"沪深300ETF"' in json_str
