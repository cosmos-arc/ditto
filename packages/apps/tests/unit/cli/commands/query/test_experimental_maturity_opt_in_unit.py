"""Tests for CLI experimental query maturity opt-in pass-through."""

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
    return CliRunner()


def _patch_fundamental_facades(mocker: MockerFixture) -> MagicMock:
    from ditto_apps.cli.commands.query import fundamental

    facade = MagicMock()
    facade.get_balance_sheet.return_value = pl.DataFrame()
    metadata = MagicMock()
    metadata.resolve_instrument_identifier.return_value = 1

    @contextmanager
    def fake_facades() -> Any:
        yield facade, metadata

    mocker.patch.object(fundamental, "_get_facades", fake_facades)
    return facade


def _patch_capital_facades(mocker: MockerFixture) -> MagicMock:
    from ditto_apps.cli.commands.query import capital

    facade = MagicMock()
    facade.get_margin_trading.return_value = pl.DataFrame()
    metadata = MagicMock()
    metadata.resolve_instrument_identifier.return_value = 1

    @contextmanager
    def fake_facades() -> Any:
        yield facade, metadata

    mocker.patch.object(capital, "_get_facades", fake_facades)
    return facade


def _patch_macro_facade(mocker: MockerFixture) -> MagicMock:
    from ditto_apps.cli.commands.query import macro

    facade = MagicMock()
    facade.find_indicators.return_value = pl.DataFrame()

    @contextmanager
    def fake_facade() -> Any:
        yield facade

    mocker.patch.object(macro, "_get_macro_facade", fake_facade)
    return facade


@pytest.mark.unit
def test_fundamental_financials_passes_allow_experimental_data_flag(
    runner: CliRunner,
    mocker: MockerFixture,
) -> None:
    facade = _patch_fundamental_facades(mocker)

    result = runner.invoke(
        app,
        [
            "query",
            "fundamental",
            "financials",
            "--instrument-id",
            "1",
            "--date",
            "2026-06-01",
            "--allow-experimental-data",
        ],
    )

    assert result.exit_code == 0
    facade.get_balance_sheet.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


@pytest.mark.unit
def test_capital_margin_passes_allow_experimental_data_flag(
    runner: CliRunner,
    mocker: MockerFixture,
) -> None:
    facade = _patch_capital_facades(mocker)

    result = runner.invoke(
        app,
        [
            "query",
            "capital",
            "margin",
            "--instrument-id",
            "1",
            "--date",
            "2026-06-01",
            "--allow-experimental-data",
        ],
    )

    assert result.exit_code == 0
    facade.get_margin_trading.assert_called_once_with(
        1,
        date(2026, 6, 1),
        allow_experimental_data=True,
    )


@pytest.mark.unit
def test_macro_indicators_passes_allow_experimental_data_flag(
    runner: CliRunner,
    mocker: MockerFixture,
) -> None:
    facade = _patch_macro_facade(mocker)

    result = runner.invoke(
        app,
        [
            "query",
            "macro",
            "indicators",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-06-01",
            "--allow-experimental-data",
        ],
    )

    assert result.exit_code == 0
    facade.find_indicators.assert_called_once_with(
        start="2026-01-01",
        end="2026-06-01",
        category=None,
        frequency=None,
        allow_experimental_data=True,
    )
