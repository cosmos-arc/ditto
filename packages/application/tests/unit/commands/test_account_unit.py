"""Account baseline command tests."""

from __future__ import annotations

import inspect
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.account import (
    ImportAccountBaselineCommand,
    ImportAccountBaselineHandler,
    PositionBaselineInput,
)
from ditto_application.exceptions import AppCommandError
from ditto_execution.models import AccountSnapshotRecord, PositionRecord


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


def _handler(
    account_port: MagicMock,
    position_port: MagicMock | None = None,
) -> ImportAccountBaselineHandler:
    return ImportAccountBaselineHandler(
        account_port=account_port,
        position_port=position_port if position_port is not None else MagicMock(),
    )


def test_import_uses_stable_manual_sleeve_and_snapshot_identity() -> None:
    port = MagicMock()
    port.list_account_snapshots.return_value = []
    handler = _handler(port)

    first = handler.handle(_command())
    second = handler.handle(_command())

    assert first.sleeve_id == "manual-paper-a-seed_etf_industry_rotation"
    assert first.snapshot_id == second.snapshot_id
    saved_account = port.save_account_baseline.call_args.kwargs["account"]
    assert saved_account.run_id == first.sleeve_id
    assert saved_account.exposure == 40_000.0


def test_identical_existing_baseline_is_noop() -> None:
    port = MagicMock()
    position_port = MagicMock()
    command = _command()
    initial_handler = _handler(port, position_port)
    port.list_account_snapshots.return_value = []
    created = initial_handler.handle(command)
    saved = port.save_account_baseline.call_args.kwargs["account"]
    saved_positions = port.save_account_baseline.call_args.kwargs["positions"]
    port.reset_mock()
    port.list_account_snapshots.return_value = [saved]
    position_port.list_positions.return_value = saved_positions

    replay = initial_handler.handle(command)

    assert replay.snapshot_id == created.snapshot_id
    assert replay.status == "unchanged"
    port.save_account_baseline.assert_not_called()


def test_identical_replay_fails_closed_when_owned_positions_are_missing() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    command = _command()
    handler = _handler(account_port, position_port)
    account_port.list_account_snapshots.return_value = []
    handler.handle(command)
    saved = account_port.save_account_baseline.call_args.kwargs["account"]
    account_port.reset_mock()
    account_port.list_account_snapshots.return_value = [saved]
    position_port.list_positions.return_value = [
        PositionRecord(
            snapshot_id=f"{saved.snapshot_id}-shadow-510300",
            run_id=saved.run_id,
            strategy_id=saved.strategy_id,
            snapshot_date=saved.snapshot_date,
            instrument_id=510300,
            quantity=1000,
            available_quantity=1000,
            average_cost=39.0,
            market_value=saved.exposure,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
    ]

    with pytest.raises(AppCommandError, match=r"incomplete|inconsistent"):
        handler.handle(command)

    account_port.save_account_baseline.assert_not_called()


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
    handler = _handler(port)

    with pytest.raises(AppCommandError, match="replace_confirmed"):
        handler.handle(_command())

    port.save_account_baseline.assert_not_called()


def test_invalid_snapshot_date_fails_before_storage() -> None:
    """Baseline identity must use a real ISO calendar date."""
    port = MagicMock()
    handler = _handler(port)

    with pytest.raises(AppCommandError, match="snapshot_date"):
        handler.handle(_command(snapshot_date="2026-02-30"))

    port.save_account_baseline.assert_not_called()


def test_confirmed_replacement_audit_captures_old_account_and_positions() -> None:
    """Correction audit must retain the complete superseded baseline."""
    account_port = MagicMock()
    position_port = MagicMock()
    old_account = AccountSnapshotRecord(
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
    old_position = PositionRecord(
        snapshot_id="old-510300",
        run_id=old_account.run_id,
        strategy_id=old_account.strategy_id,
        snapshot_date=old_account.snapshot_date,
        instrument_id=510300,
        quantity=1200,
        available_quantity=1200,
        average_cost=40.0,
        market_value=50_000.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )
    account_port.list_account_snapshots.return_value = [old_account]
    position_port.list_positions.return_value = [old_position]
    handler = ImportAccountBaselineHandler(
        account_port=account_port,
        position_port=position_port,
    )

    result = handler.handle(_command(replace_confirmed=True))

    assert result.status == "replaced"
    audit = account_port.save_account_baseline.call_args.kwargs["audit_payload"]
    assert audit.old_baseline is not None
    assert audit.old_baseline["snapshot_id"] == "old"
    assert audit.old_baseline["positions"] == [
        {
            "instrument_id": 510300,
            "quantity": 1200,
            "available_quantity": 1200,
            "average_cost": 40.0,
            "market_value": 50_000.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "total_fees": 0.0,
        }
    ]


def test_replacement_fails_closed_when_old_position_evidence_is_missing() -> None:
    """A non-empty superseded account cannot be audited with an empty position set."""
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
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
    position_port.list_positions.return_value = []
    handler = ImportAccountBaselineHandler(
        account_port=account_port,
        position_port=position_port,
    )

    with pytest.raises(AppCommandError, match=r"positions.*audit"):
        handler.handle(_command(replace_confirmed=True))

    account_port.save_account_baseline.assert_not_called()


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
    handler = _handler(port)

    with pytest.raises(AppCommandError, match=message):
        handler.handle(_command(**overrides))

    port.save_account_baseline.assert_not_called()


def test_position_port_is_a_required_handler_dependency() -> None:
    """Replacement audit must never silently omit superseded positions."""
    parameter = inspect.signature(ImportAccountBaselineHandler).parameters[
        "position_port"
    ]

    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize(
    "field_name",
    [
        "cash_available",
        "cash_settled",
        "cash_frozen",
        "total_value",
        "nav",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_account_amount_fails_before_storage(
    field_name: str,
    value: float,
) -> None:
    port = MagicMock()
    handler = _handler(port)

    with pytest.raises(AppCommandError, match=field_name):
        handler.handle(_command(**{field_name: value}))

    port.save_account_baseline.assert_not_called()


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "available_quantity",
        "average_cost",
        "market_value",
        "unrealized_pnl",
        "realized_pnl",
        "total_fees",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_position_value_fails_before_storage(
    field_name: str,
    value: float,
) -> None:
    port = MagicMock()
    handler = _handler(port)
    position = replace(
        _command().positions[0],
        **{field_name: value},
    )

    with pytest.raises(AppCommandError, match=field_name):
        handler.handle(_command(positions=(position,)))

    port.save_account_baseline.assert_not_called()
