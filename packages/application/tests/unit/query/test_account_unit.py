"""Account baseline query tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.queries.account import AccountBaselineQuery
from ditto_execution.models import AccountSnapshotRecord, PositionRecord


def _account(
    snapshot_date: str,
    snapshot_id: str,
    *,
    exposure: float = 0.0,
    created_at: str = "",
) -> AccountSnapshotRecord:
    return AccountSnapshotRecord(
        snapshot_id=snapshot_id,
        run_id="manual-paper-a-strategy-a",
        strategy_id="strategy-a",
        account_id="paper-a",
        snapshot_date=snapshot_date,
        cash_available=100.0,
        cash_settled=100.0,
        cash_frozen=0.0,
        total_value=100.0 + exposure,
        nav=1.0,
        exposure=exposure,
        created_at=created_at,
    )


def _position(
    owner_snapshot_id: str,
    *,
    instrument_id: int = 510300,
    market_value: float = 100.0,
    snapshot_date: str = "2026-07-15",
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=f"{owner_snapshot_id}-{instrument_id}",
        run_id="manual-paper-a-strategy-a",
        strategy_id="strategy-a",
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=100,
        available_quantity=100,
        average_cost=1.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def test_returns_latest_complete_baseline_not_later_than_signal_date() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-14", "old"),
        _account("2026-07-15", "selected", exposure=100.0),
        _account("2026-07-16", "future"),
    ]
    position_port.list_positions.return_value = [_position("selected")]
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


def test_zero_exposure_account_with_empty_positions_is_complete() -> None:
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


def test_returns_only_positions_owned_by_selected_account_snapshot() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-15", "selected", exposure=100.0)
    ]
    position_port.list_positions.return_value = [
        _position("foreign", instrument_id=159915, market_value=900.0),
        _position("selected", market_value=100.0),
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
    assert [position.snapshot_id for position in result.positions] == [
        "selected-510300"
    ]


def test_rejects_positive_exposure_snapshot_without_owned_positions() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-15", "selected", exposure=100.0)
    ]
    position_port.list_positions.return_value = [
        _position("foreign", market_value=100.0)
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

    assert result is None


def test_rejects_snapshot_when_owned_market_value_does_not_match_exposure() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-15", "selected", exposure=100.0)
    ]
    position_port.list_positions.return_value = [
        _position("selected", market_value=99.0)
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

    assert result is None


def test_falls_back_to_latest_complete_snapshot_when_newer_one_is_incomplete() -> None:
    account_port = MagicMock()
    position_port = MagicMock()
    account_port.list_account_snapshots.return_value = [
        _account("2026-07-14", "complete", exposure=80.0),
        _account("2026-07-15", "incomplete", exposure=100.0),
    ]
    position_port.list_positions.side_effect = lambda **filters: (
        []
        if filters["snapshot_date"] == "2026-07-15"
        else [
            _position(
                "complete",
                market_value=80.0,
                snapshot_date="2026-07-14",
            )
        ]
    )
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
    assert result.account.snapshot_id == "complete"
    assert result.positions[0].snapshot_date == "2026-07-14"
