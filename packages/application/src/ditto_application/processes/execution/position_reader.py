"""PositionReader adapter backed by stored manual position snapshots."""

from __future__ import annotations

from ditto_execution.contracts import PositionDataPort

__all__ = ["StoredPositionReader"]


class StoredPositionReader:
    """Convert latest stored position market values into current weights."""

    def __init__(self, position_port: PositionDataPort) -> None:
        self._position_port = position_port

    def get_current_positions(self, strategy_id: str) -> dict[int, float]:
        """Get current position weights for a strategy from the latest snapshot."""
        rows = self._position_port.list_positions(strategy_id=strategy_id)
        if not rows:
            return {}

        latest_date = max(row.snapshot_date for row in rows)
        latest_rows = [row for row in rows if row.snapshot_date == latest_date]
        total_value = sum(row.market_value for row in latest_rows)
        if total_value <= 0:
            return {}

        return {
            row.instrument_id: row.market_value / total_value
            for row in sorted(latest_rows, key=lambda item: item.instrument_id)
            if row.market_value > 0
        }
