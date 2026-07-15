"""Account baseline command tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.exceptions import AppCommandError
from ditto_execution.models import AccountSnapshotRecord


def _command(**overrides: object) -> ImportAccountBaselineCommand:
    values: dict[str, object] = {
        "account_id": "paper-a",
        "strategy_id": "seed_etf_industry_rotation",
        "snapshot_date": "2026-07-15",
        "cash_available": 60_000.0,
        "cash_settled": 60_000.0,
        "cash_frozen": 0.0,
        "total_value": 100_000.0,
        "nav": 1.0,
        "positions": (
            PositionBaselineInput(
                instrument_id=510300,
                quantity=1000,
                available_quantity=1000,
                average_cost=39.0,
                market_value=40_000.0,
            ),
        ),
    }
    values.update(overrides)
    return ImportAccountBaselineCommand(**values)  # type: ignore[arg-type]


def test_import_uses_stable_manual_sleeve_and_snapshot_identity() -> None:
    port = MagicMock()
    port.list_account_snapshots.return_value = []
    handler = ImportAccountBaselineHandler(account_port=port)

    first = handler.handle(_command())
    second = handler.handle(_command())

    assert first.sleeve_id == "manual-paper-a-seed_etf_industry_rotation"
    assert first.snapshot_id == second.snapshot_id
    saved_account = port.save_account_baseline.call_args.kwargs["account"]
    assert saved_account.run_id == first.sleeve_id
    assert saved_account.exposure == 40_000.0


def test_identical_existing_baseline_is_noop() -> None:
    port = MagicMock()
    command = _command()
    initial_handler = ImportAccountBaselineHandler(account_port=port)
    port.list_account_snapshots.return_value = []
    created = initial_handler.handle(command)
    saved = port.save_account_baseline.call_args.kwargs["account"]
    port.reset_mock()
    port.list_account_snapshots.return_value = [saved]

    replay = initial_handler.handle(command)

    assert replay.snapshot_id == created.snapshot_id
    assert replay.status == "unchanged"
    port.save_account_baseline.assert_not_called()


def test_changed_existing_baseline_requires_explicit_replacement() -> None:
    port = MagicMock()
    port.list_account_snapshots.return_value = [
        AccountSnapshotRecord(
            snapshot_id="old",
            run_id="manual-paper-a-seed_etf_industry_rotation",
            strategy_id="seed_etf_industry_rotation",
            account_id="paper-a",
            snapshot_date="2026-07-15",
            cash_available=50_000.0,
            cash_settled=50_000.0,
            cash_frozen=0.0,
            total_value=100_000.0,
            nav=1.0,
            exposure=50_000.0,
        )
    ]
    handler = ImportAccountBaselineHandler(account_port=port)

    with pytest.raises(AppCommandError, match="replace_confirmed"):
        handler.handle(_command())

    port.save_account_baseline.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cash_available": -1.0}, "cash_available"),
        ({"total_value": -1.0}, "total_value"),
        (
            {
                "positions": (
                    PositionBaselineInput(
                        instrument_id=510300,
                        quantity=100,
                        available_quantity=101,
                        average_cost=1.0,
                        market_value=100.0,
                    ),
                )
            },
            "available_quantity",
        ),
    ],
)
def test_invalid_baseline_fails_before_storage(
    overrides: dict[str, object], message: str
) -> None:
    port = MagicMock()
    handler = ImportAccountBaselineHandler(account_port=port)

    with pytest.raises(AppCommandError, match=message):
        handler.handle(_command(**overrides))

    port.save_account_baseline.assert_not_called()
