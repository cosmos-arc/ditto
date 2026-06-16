"""StoredPositionReader unit tests."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_application.processes.execution.position_reader import StoredPositionReader
from ditto_execution.models import PositionRecord


@dataclass
class _PositionPort:
    rows: list[PositionRecord]

    def list_positions(
        self,
        strategy_id: str,
        snapshot_date: str | None = None,
        run_id: str | None = None,
    ) -> list[PositionRecord]:
        assert strategy_id == "stock-selection"
        assert snapshot_date is None
        assert run_id is None
        return self.rows


def _row(
    instrument_id: int,
    snapshot_date: str,
    market_value: float,
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=f"p-{instrument_id}-{snapshot_date}",
        strategy_id="stock-selection",
        snapshot_date=snapshot_date,
        instrument_id=instrument_id,
        quantity=100,
        available_quantity=100,
        average_cost=10.0,
        market_value=market_value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def test_latest_snapshot_market_values_become_weights() -> None:
    reader = StoredPositionReader(
        position_port=_PositionPort(
            [
                _row(1, "2026-01-05", 900.0),
                _row(1, "2026-01-06", 600.0),
                _row(2, "2026-01-06", 400.0),
            ]
        )
    )

    result = reader.get_current_positions("stock-selection")

    assert result == {1: 0.6, 2: 0.4}


def test_empty_or_zero_market_value_returns_empty_weights() -> None:
    assert (
        StoredPositionReader(position_port=_PositionPort([])).get_current_positions(
            "stock-selection"
        )
        == {}
    )
    assert (
        StoredPositionReader(
            position_port=_PositionPort([_row(1, "2026-01-06", 0.0)])
        ).get_current_positions("stock-selection")
        == {}
    )
