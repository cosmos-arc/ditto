"""Tests for ExchangeTransformer Protocol and ExchangeTransformers factory."""

from typing import TYPE_CHECKING

import pytest
from ditto_data.sources import ExchangeTransformer, ExchangeTransformers
from pytest_mock import MockerFixture

if TYPE_CHECKING:
    pass


class TestExchangeTransformerProtocol:
    """Tests for ExchangeTransformer Protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Test that ExchangeTransformer is runtime checkable."""

        class MockTransformer:
            def to_standard(self, source_ticker: str) -> str:
                return source_ticker.replace(".SZ", ".XSHE")

            def from_standard(self, standard_ticker: str) -> str:
                return standard_ticker.replace(".XSHE", ".SZ")

        transformer = MockTransformer()
        # Protocol with @runtime_checkable allows isinstance check
        assert isinstance(transformer, ExchangeTransformer)

    def test_protocol_methods_signature(self) -> None:
        """Test that protocol defines expected methods."""

        class CompleteTransformer:
            def to_standard(self, source_ticker: str) -> str:
                return f"std_{source_ticker}"

            def from_standard(self, standard_ticker: str) -> str:
                return f"src_{standard_ticker}"

        transformer = CompleteTransformer()
        # Should have both methods
        assert hasattr(transformer, "to_standard")
        assert hasattr(transformer, "from_standard")
        assert callable(transformer.to_standard)
        assert callable(transformer.from_standard)


class TestExchangeTransformers:
    """Tests for ExchangeTransformers factory."""

    def test_tushare_property_returns_transformer(self, mocker: MockerFixture) -> None:
        """Test tushare property returns the injected transformer."""
        mock_tushare = mocker.Mock()
        mock_tushare.to_standard = mocker.Mock(return_value="000001.XSHE")
        mock_tushare.from_standard = mocker.Mock(return_value="000001.SZ")

        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)
        result = transformers.tushare

        assert result is mock_tushare
        assert result.to_standard("000001.SZ") == "000001.XSHE"

    def test_tdx_property_returns_transformer(self, mocker: MockerFixture) -> None:
        """Test tdx property returns the injected transformer."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()
        mock_tdx.to_standard = mocker.Mock(return_value="000001.XSHE")
        mock_tdx.from_standard = mocker.Mock(return_value="000001.SZ")

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)
        result = transformers.tdx

        assert result is mock_tdx
        assert result.to_standard("000001.SZ") == "000001.XSHE"

    def test_get_returns_tushare_transformer(self, mocker: MockerFixture) -> None:
        """Test get() method returns tushare transformer."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)
        result = transformers.get("tushare")

        assert result is mock_tushare

    def test_get_returns_tdx_transformer(self, mocker: MockerFixture) -> None:
        """Test get() method returns tdx transformer."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)
        result = transformers.get("tdx")

        assert result is mock_tdx

    def test_get_is_case_insensitive(self, mocker: MockerFixture) -> None:
        """Test get() normalizes case."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)

        result1 = transformers.get("TUSHARE")
        result2 = transformers.get("tushare")
        result3 = transformers.get("  tushare  ")

        assert result1 is mock_tushare
        assert result2 is mock_tushare
        assert result3 is mock_tushare

    def test_get_tdx_is_case_insensitive(self, mocker: MockerFixture) -> None:
        """Test get() normalizes case for tdx."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)

        result1 = transformers.get("TDX")
        result2 = transformers.get("tdx")
        result3 = transformers.get("  tdx  ")

        assert result1 is mock_tdx
        assert result2 is mock_tdx
        assert result3 is mock_tdx

    def test_get_invalid_name_raises_error(self, mocker: MockerFixture) -> None:
        """Test get() raises error for invalid source name."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)

        with pytest.raises(ValueError, match="Unknown source"):
            transformers.get("invalid_source")

    def test_get_returns_exchange_transformer_protocol(
        self, mocker: MockerFixture
    ) -> None:
        """Test get() returns ExchangeTransformer protocol compliant object."""
        mock_tushare = mocker.Mock()
        mock_tushare.to_standard = mocker.Mock(return_value="000001.XSHE")
        mock_tushare.from_standard = mocker.Mock(return_value="000001.SZ")
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)
        result = transformers.get("tushare")

        # Should be usable as ExchangeTransformer
        assert isinstance(result, ExchangeTransformer)
        assert result.to_standard("000001.SZ") == "000001.XSHE"
        assert result.from_standard("000001.XSHE") == "000001.SZ"

    def test_properties_return_same_instance(self, mocker: MockerFixture) -> None:
        """Test properties return the same instance on multiple calls."""
        mock_tushare = mocker.Mock()
        mock_tdx = mocker.Mock()

        transformers = ExchangeTransformers(tushare=mock_tushare, tdx=mock_tdx)

        # Properties should return same instance
        assert transformers.tushare is transformers.tushare
        assert transformers.tdx is transformers.tdx
