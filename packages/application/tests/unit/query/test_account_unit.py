"""Account baseline query tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.queries.account import AccountBaselineQuery
from ditto_execution.models import AccountSnapshotRecord, PositionRecord


def _account(snapshot_date: str, snapshot_id: str) -> AccountSnapshotRecord:
    return AccountSnapshotRecord(
        snapshot_id=snapshot_id,
        run_id="manual-paper-a-strategy-a",
        strategy_id="strategy-a",
        account_id="paper-a",
        snapshot_date=snapshot_date,
        cash_available=100.0,
        cash_settled=100.0,
        cash_frozen=0.0,
        total_value=100.0,
        nav=1.0,
        exposure=0.0,
    )


def test_returns_latest_complete_baseline_not_later_than_signal_date() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-14", "old"),
        _account("2026-07-15", "selected"),
        _account("2026-07-16", "future"),
    ]
    position_port.list_positions.return_value = [
        PositionRecord(
            snapshot_id="position-selected",
            run_id="manual-paper-a-strategy-a",
            strategy_id="strategy-a",
            snapshot_date="2026-07-15",
            instrument_id=510300,
            quantity=100,
            available_quantity=100,
            average_cost=1.0,
            market_value=100.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=0.0,
        )
    ]
    query = AccountBaselineQuery(
        account_port=account_port,
        position_port=position_port,
    )

    result = query.get_latest(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-07-15",
    )

    assert result is not None
    assert result.account.snapshot_id == "selected"
    assert result.positions[0].snapshot_date == "2026-07-15"
    position_port.list_positions.assert_called_once_with(
        strategy_id="strategy-a",
        snapshot_date="2026-07-15",
        run_id="manual-paper-a-strategy-a",
    )


def test_does_not_combine_account_and_positions_from_different_dates() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-15", "selected")
    ]
    position_port.list_positions.return_value = []
    query = AccountBaselineQuery(
        account_port=account_port,
        position_port=position_port,
    )

    result = query.get_latest(
        account_id="paper-a",
        strategy_id="strategy-a",
        signal_date="2026-07-15",
    )

    assert result is not None
    assert result.positions == ()
