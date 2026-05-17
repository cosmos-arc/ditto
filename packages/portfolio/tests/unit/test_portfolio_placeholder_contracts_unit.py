"""Tests for minimal portfolio capability contracts."""

from typing import Protocol

from ditto_kernel.identity import InstrumentId
from ditto_portfolio.holdings import HoldingReader, HoldingSnapshot
from ditto_portfolio.positions import PositionReader, PositionSnapshot

IID = InstrumentId(510300)


def test_holding_reader_contract_is_actionable() -> None:
    assert issubclass(HoldingReader, Protocol)
    assert hasattr(HoldingReader, "get_holding")
    assert hasattr(HoldingReader, "list_holdings")


def test_holding_snapshot_captures_valuation_state() -> None:
    snapshot = HoldingSnapshot(
        account_id="acct-1",
        snapshot_date="2026-05-05",
        instrument_id=IID,
        quantity=100,
        available_quantity=100,
        market_value=512.3,
        weight=0.25,
    )

    assert snapshot.available_quantity == 100


def test_position_reader_contract_is_actionable() -> None:
    assert issubclass(PositionReader, Protocol)
    assert hasattr(PositionReader, "get_position")
    assert hasattr(PositionReader, "list_positions")


def test_position_snapshot_captures_lifecycle_state() -> None:
    snapshot = PositionSnapshot(
        portfolio_id="portfolio-1",
        snapshot_date="2026-05-05",
        instrument_id=IID,
        quantity=100,
        average_cost=4.95,
        market_value=512.3,
    )

    assert snapshot.status == "open"
