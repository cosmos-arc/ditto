"""Tests for shared API identifier resolution utility."""

from unittest.mock import MagicMock

import pytest
from ditto_interfaces.api.errors import APIError, BadRequestError
from ditto_interfaces.api.utils.identifier import resolve_identifier_for_api
from ditto_kernel import AmbiguousTickerError, NoIdentifierProvidedError


@pytest.mark.unit
class TestResolveIdentifierForApi:
    """Test the shared resolve_identifier_for_api utility."""

    def test_no_identifier_raises_400(self) -> None:
        """No identifier provided should raise BadRequestError 400."""
        mock_meta = MagicMock()
        with pytest.raises(BadRequestError) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker=None,
            )
        assert exc_info.value.status_code == 400

    def test_ambiguous_ticker_raises_400(self) -> None:
        """AmbiguousTickerError should raise BadRequestError 400."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = AmbiguousTickerError(
            ticker="000001", matches=[]
        )
        with pytest.raises(BadRequestError) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker="000001",
            )
        assert exc_info.value.status_code == 400

    def test_no_identifier_provided_error_raises_400(self) -> None:
        """NoIdentifierProvidedError should raise BadRequestError 400."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = NoIdentifierProvidedError(
            "no identifier"
        )
        with pytest.raises(BadRequestError) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker="000001.XSHE",
                ticker=None,
            )
        assert exc_info.value.status_code == 400

    def test_unexpected_error_raises_500(self) -> None:
        """Unexpected exceptions should raise APIError 500."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = RuntimeError("db error")
        with pytest.raises(APIError) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker="000001",
                domain="capital",
            )
        assert exc_info.value.status_code == 500
