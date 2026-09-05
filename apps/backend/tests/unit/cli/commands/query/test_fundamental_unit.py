"""Fundamental query CLI command behavior tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_apps.cli.main import app
from pytest_mock import MockerFixture
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner."""
    return CliRunner()


def _financial_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "report_date": ["2024-12-31"],
            "data": [{"total_assets": 1_000_000.0}],
        }
    )


def _dividend_df(amount: float = 0.5) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "announce_date": ["2024-05-01"],
            "dividend_type": ["cash"],
            "amount": [amount],
        }
    )


def _corporate_actions_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "action_date": ["2024-05-01"],
            "action_type": ["dividend"],
            "description": ["cash dividend"],
        }
    )


def _patch_facades(
    mocker: MockerFixture,
    *,
    fundamental_facade: MagicMock | None = None,
    metadata_facade: MagicMock | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Patch the fundamental query context manager."""
    from ditto_apps.cli.commands.query import fundamental

    fundamental_facade = fundamental_facade or MagicMock()
    metadata_facade = metadata_facade or MagicMock()
    metadata_facade.resolve_instrument_identifier.return_value = 1_000_001

    @contextmanager
    def fake_facades() -> Any:
        yield fundamental_facade, metadata_facade

    mocker.patch.object(fundamental, "_get_facades", fake_facades)
    return fundamental_facade, metadata_facade


@pytest.mark.unit
class TestFundamentalFinancialsCommand:
    """financials command tests."""

    def test_financials_json_routes_balance_sheet(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Balance-sheet query resolves the identifier and emits JSON."""
        facade, metadata = _patch_facades(mocker)
        facade.get_balance_sheet.return_value = _financial_df()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "financials",
                "--instrument-id",
                "1000001",
                "--type",
                "balance_sheet",
                "--date",
                "2024-12-31",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert '"instrument_id": 1000001' in result.output
        assert '"report_type": "balance_sheet"' in result.output
        metadata.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
            asof="2024-12-31",
        )
        facade.get_balance_sheet.assert_called_once_with(1_000_001, date(2024, 12, 31))

    @pytest.mark.parametrize(
        ("report_type", "method_name"),
        [
            ("income_statement", "get_income_statement"),
            ("cash_flow", "get_cash_flow"),
        ],
    )
    def test_financials_routes_non_balance_report_types(
        self,
        runner: CliRunner,
        mocker: MockerFixture,
        report_type: str,
        method_name: str,
    ) -> None:
        """Financial type selection calls the matching facade method."""
        facade, _metadata = _patch_facades(mocker)
        getattr(facade, method_name).return_value = _financial_df()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "financials",
                "--ticker",
                "000001",
                "--type",
                report_type,
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        getattr(facade, method_name).assert_called_once_with(
            1_000_001, date(2024, 12, 31)
        )

    def test_financials_rejects_unknown_report_type(self, runner: CliRunner) -> None:
        """Unknown financial report types exit before opening facades."""
        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "financials",
                "--instrument-id",
                "1000001",
                "--type",
                "bad_type",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 1
        assert "无效的报表类型" in result.output

    def test_financials_unresolved_identifier_prints_empty_message(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Unresolved identifiers do not call the fundamental facade."""
        facade, metadata = _patch_facades(mocker)
        metadata.resolve_instrument_identifier.return_value = None

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "financials",
                "--ticker",
                "999999",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到匹配的标的" in result.output
        facade.get_balance_sheet.assert_not_called()

    @pytest.mark.parametrize("empty_value", [None, pl.DataFrame()])
    def test_financials_empty_result_prints_no_data(
        self, runner: CliRunner, mocker: MockerFixture, empty_value: pl.DataFrame | None
    ) -> None:
        """None or empty financial data prints the no-data message."""
        facade, _metadata = _patch_facades(mocker)
        facade.get_balance_sheet.return_value = empty_value

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "financials",
                "--instrument-id",
                "1000001",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到财务数据" in result.output


@pytest.mark.unit
class TestFundamentalDividendCommand:
    """dividend command tests."""

    def test_dividend_json_routes_query(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Dividend query resolves the identifier and emits JSON."""
        facade, metadata = _patch_facades(mocker)
        facade.get_dividend.return_value = _dividend_df()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "dividend",
                "--standard-ticker",
                "000001.XSHE",
                "--date",
                "2024-12-31",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert '"dividend_type": "cash"' in result.output
        metadata.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=None,
            standard_ticker="000001.XSHE",
            ticker=None,
            asof="2024-12-31",
        )
        facade.get_dividend.assert_called_once_with(1_000_001, date(2024, 12, 31))

    def test_dividend_unresolved_identifier_prints_empty_message(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Unresolved dividend identifiers do not call the fundamental facade."""
        facade, metadata = _patch_facades(mocker)
        metadata.resolve_instrument_identifier.return_value = None

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "dividend",
                "--ticker",
                "999999",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到匹配的标的" in result.output
        facade.get_dividend.assert_not_called()

    @pytest.mark.parametrize("empty_value", [None, pl.DataFrame()])
    def test_dividend_empty_result_prints_no_data(
        self, runner: CliRunner, mocker: MockerFixture, empty_value: pl.DataFrame | None
    ) -> None:
        """None or empty dividend data prints the no-data message."""
        facade, _metadata = _patch_facades(mocker)
        facade.get_dividend.return_value = empty_value

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "dividend",
                "--instrument-id",
                "1000001",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到分红数据" in result.output

    def test_dividend_table_renders_zero_amount_as_dash(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Table output uses the fallback display for zero dividend amounts."""
        facade, _metadata = _patch_facades(mocker)
        facade.get_dividend.return_value = _dividend_df(amount=0.0)

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "dividend",
                "--instrument-id",
                "1000001",
                "--date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "分红数据" in result.output
        assert "cash" in result.output


@pytest.mark.unit
class TestFundamentalCorporateActionsCommand:
    """corporate-actions command tests."""

    def test_corporate_actions_accepts_as_of_date_for_pit_query(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Corporate-action CLI forwards optional PIT date to resolution and query."""
        facade, metadata = _patch_facades(mocker)
        facade.list_corporate_actions.return_value = _corporate_actions_df()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "corporate-actions",
                "--instrument-id",
                "1000001",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-12-31",
                "--as-of-date",
                "2024-06-30",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert '"action_type": "dividend"' in result.output
        metadata.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
            asof="2024-06-30",
        )
        facade.list_corporate_actions.assert_called_once_with(
            1_000_001,
            date(2024, 1, 1),
            date(2024, 12, 31),
            date(2024, 6, 30),
        )

    def test_corporate_actions_without_as_of_date_keeps_query_unversioned(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Omitting --as-of-date preserves the facade's unversioned query behavior."""
        facade, metadata = _patch_facades(mocker)
        facade.list_corporate_actions.return_value = _corporate_actions_df()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "corporate-actions",
                "--ticker",
                "000001",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "公司行动" in result.output
        assert "dividend" in result.output
        metadata.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=None,
            standard_ticker=None,
            ticker="000001",
            asof=None,
        )
        facade.list_corporate_actions.assert_called_once_with(
            1_000_001,
            date(2024, 1, 1),
            date(2024, 12, 31),
            None,
        )

    def test_corporate_actions_unresolved_identifier_prints_empty_message(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Unresolved corporate-action identifiers do not call the facade."""
        facade, metadata = _patch_facades(mocker)
        metadata.resolve_instrument_identifier.return_value = None

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "corporate-actions",
                "--standard-ticker",
                "999999.XSHG",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到匹配的标的" in result.output
        facade.list_corporate_actions.assert_not_called()

    def test_corporate_actions_empty_result_prints_no_data(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """Empty corporate-action data prints the no-data message."""
        facade, _metadata = _patch_facades(mocker)
        facade.list_corporate_actions.return_value = pl.DataFrame()

        result = runner.invoke(
            app,
            [
                "query",
                "fundamental",
                "corporate-actions",
                "--instrument-id",
                "1000001",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-12-31",
            ],
        )

        assert result.exit_code == 0
        assert "未找到公司行动数据" in result.output
