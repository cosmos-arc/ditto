"""Portfolio package domain events unit tests."""

from datetime import datetime

from ditto_portfolio.events import PositionChanged


class TestPositionChanged:
    def test_creation(self) -> None:
        event = PositionChanged(
            timestamp=datetime(2024, 1, 15, 15, 0),
            instrument_id=600000,
            quantity_change=100.0,
            new_quantity=200.0,
        )
        assert event.event_type == "position_changed"
        assert event.new_quantity == 200.0
