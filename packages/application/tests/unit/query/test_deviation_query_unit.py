"""Unit tests for signal-to-fill deviation query semantics."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.queries.deviation import SignalDeviationQueryFacade
from ditto_execution.models import FillRecord, PositionRecord, SignalRecord


def _intent(intent_id: str) -> SignalRecord:
    return SignalRecord(
        intent_id=intent_id,
        strategy_id="strat-a",
        signal_date="2024-01-15",
        instrument_id=510300,
        direction="buy",
        target_weight=0.3,
        current_weight=0.1,
        delta_weight=0.2,
        quantity=1000,
    )


def _fill(intent_id: str) -> FillRecord:
    return FillRecord(
        fill_id=f"fill-{intent_id}",
        intent_id=intent_id,
        strategy_id="strat-a",
        trade_date="2024-01-16",
        instrument_id=510300,
        direction="buy",
        quantity=400,
        fill_price=4.2,
        fee=1.0,
    )


def _position() -> PositionRecord:
    return PositionRecord(
        snapshot_id="position-d1",
        strategy_id="strat-a",
        snapshot_date="2024-01-16",
        instrument_id=510300,
        quantity=400,
        available_quantity=0,
        average_cost=4.2,
        market_value=1680.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=1.0,
    )


def test_deviation_uses_explicit_execution_date_for_d_plus_one_fills() -> None:
    intent_port = MagicMock()
    intent_port.list_intents.return_value = [_intent("intent-rev2")]
    fill_port = MagicMock()
    fill_port.list_effective_fills.return_value = [_fill("intent-rev2")]
    position_port = MagicMock()
    position_port.list_positions.return_value = [_position()]

    report = SignalDeviationQueryFacade(
        intent_port=intent_port,
        fill_port=fill_port,
        position_port=position_port,
    ).get_deviation(
        strategy_id="strat-a",
        signal_date="2024-01-15",
        execution_date="2024-01-16",
        intent_ids=("intent-rev2",),
    )

    assert report.total_signals == 1
    assert report.filled == 1
    assert report.items[0].fill_status == "filled"
    fill_port.list_effective_fills.assert_called_once_with(
        strategy_id="strat-a",
        trade_date="2024-01-16",
        end_date="2024-01-16",
    )
    position_port.list_positions.assert_called_once_with(
        strategy_id="strat-a",
        snapshot_date="2024-01-16",
    )


def test_deviation_does_not_apply_an_old_revision_fill_to_same_instrument() -> None:
    intent_port = MagicMock()
    intent_port.list_intents.return_value = [
        _intent("intent-rev1"),
        _intent("intent-rev2"),
    ]
    fill_port = MagicMock()
    fill_port.list_effective_fills.return_value = [_fill("intent-rev1")]
    position_port = MagicMock()
    position_port.list_positions.return_value = [_position()]

    report = SignalDeviationQueryFacade(
        intent_port=intent_port,
        fill_port=fill_port,
        position_port=position_port,
    ).get_deviation(
        strategy_id="strat-a",
        signal_date="2024-01-15",
        execution_date="2024-01-16",
        intent_ids=("intent-rev2",),
    )

    assert report.total_signals == 1
    assert report.filled == 0
    assert report.unfilled == 1
    assert report.items[0].instrument_id == 510300
    assert report.items[0].fill_status == "unfilled"
    assert report.items[0].actual_weight is None
    assert report.items[0].deviation_bps is None
