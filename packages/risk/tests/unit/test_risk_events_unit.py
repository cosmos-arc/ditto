"""Risk package domain events unit tests."""

from datetime import datetime

import pytest
from ditto_risk.events import RiskGuardDetails, RiskGuardTriggered


class TestRiskGuardTriggered:
    def test_creation(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15, 14, 0),
            rule_name="max_drawdown",
            severity="critical",
        )
        assert event.event_type == "risk_guard_triggered"
        assert event.severity == "critical"
        assert event.details.instrument_id is None

    def test_with_details(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15),
            rule_name="concentration_limit",
            severity="warning",
            details=RiskGuardDetails(
                instrument_id=600000,
                current_value=0.35,
                limit_value=0.30,
            ),
        )
        assert event.details.instrument_id == 600000
        assert event.details.current_value == 0.35
        assert event.details.limit_value == 0.30

    def test_details_default_empty(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15),
            rule_name="max_drawdown",
            severity="critical",
        )
        assert event.details.instrument_id is None
        assert event.details.current_value is None
        assert event.details.limit_value is None


class TestRiskGuardDetails:
    """RiskGuardDetails typed payload 测试."""

    def test_creation_minimal(self) -> None:
        details = RiskGuardDetails()
        assert details.instrument_id is None
        assert details.current_value is None
        assert details.limit_value is None
        assert details.description == ""

    def test_creation_full(self) -> None:
        details = RiskGuardDetails(
            instrument_id=600000,
            current_value=0.35,
            limit_value=0.30,
            description="concentration exceeded",
        )
        assert details.instrument_id == 600000
        assert details.current_value == 0.35
        assert details.limit_value == 0.30
        assert details.description == "concentration exceeded"

    def test_frozen(self) -> None:
        details = RiskGuardDetails(instrument_id=600000)
        with pytest.raises(AttributeError):
            details.instrument_id = 700000  # type: ignore[misc]
