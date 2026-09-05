"""Tests for shared CLI identifier resolution utility."""

from unittest.mock import MagicMock

import pytest
from ditto_apps.cli.utils.identifier import resolve_identifier_for_cli
from typer import Exit


@pytest.mark.unit
class TestResolveIdentifierForCli:
    """Test the shared resolve_identifier_for_cli utility."""

    def test_no_identifier_exits_with_code_1(self) -> None:
        """No identifier provided should exit with code 1."""
        mock_meta = MagicMock()
        with pytest.raises(Exit) as exc_info:
            resolve_identifier_for_cli(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker=None,
            )
        assert exc_info.value.exit_code == 1

    def test_instrument_id_passthrough(self) -> None:
        """Pass instrument_id directly to metadata facade."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 1_000_001
        result = resolve_identifier_for_cli(
            mock_meta,
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
        )
        assert result == 1_000_001
        mock_meta.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
            asof=None,
        )

    def test_ticker_resolution(self) -> None:
        """Resolve ticker via metadata facade."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 2_000_001
        result = resolve_identifier_for_cli(
            mock_meta,
            instrument_id=None,
            standard_ticker=None,
            ticker="510300",
        )
        assert result == 2_000_001

    def test_identifier_not_found_returns_none(self) -> None:
        """Return None when identifier is not found."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = None
        result = resolve_identifier_for_cli(
            mock_meta,
            instrument_id=None,
            standard_ticker=None,
            ticker="999999",
        )
        assert result is None

    def test_with_as_of_date(self) -> None:
        """Pass as_of_date parameter to metadata facade."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 1_000_001
        resolve_identifier_for_cli(
            mock_meta,
            instrument_id=None,
            standard_ticker="000001.XSHE",
            ticker=None,
            as_of_date="2024-12-31",
        )
        mock_meta.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=None,
            standard_ticker="000001.XSHE",
            ticker=None,
            asof="2024-12-31",
        )
