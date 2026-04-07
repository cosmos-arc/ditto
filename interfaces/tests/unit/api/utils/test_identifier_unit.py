"""Tests for shared API identifier resolution utility."""

from unittest.mock import MagicMock

import pytest
from ditto_app.types import AmbiguousTickerError, NoIdentifierProvidedError
from ditto_interfaces.api.utils.identifier import resolve_identifier_for_api
from fastapi import HTTPException


@pytest.mark.unit
class TestResolveIdentifierForApi:
    """Test the shared resolve_identifier_for_api utility."""

    def test_no_identifier_raises_422(self) -> None:
        """No identifier provided should raise HTTPException 422."""
        mock_meta = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker=None,
            )
        assert exc_info.value.status_code == 422

    def test_ambiguous_ticker_raises_400(self) -> None:
        """AmbiguousTickerError should raise HTTPException 400."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = AmbiguousTickerError(
            ticker="000001", matches=[]
        )
        with pytest.raises(HTTPException) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker="000001",
            )
        assert exc_info.value.status_code == 400

    def test_no_identifier_provided_error_raises_400(self) -> None:
        """NoIdentifierProvidedError should raise HTTPException 400."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = NoIdentifierProvidedError(
            "no identifier"
        )
        with pytest.raises(HTTPException) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker="000001.XSHE",
                ticker=None,
            )
        assert exc_info.value.status_code == 400

    def test_unexpected_error_raises_500(self) -> None:
        """Unexpected exceptions should raise HTTPException 500."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = RuntimeError("db error")
        with pytest.raises(HTTPException) as exc_info:
            resolve_identifier_for_api(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker="000001",
                domain="capital",
            )
        assert exc_info.value.status_code == 500
