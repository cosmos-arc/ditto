"""Risk package domain events unit tests."""

from datetime import datetime

from ditto_risk.events import RiskGuardTriggered


class TestRiskGuardTriggered:
    def test_creation(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15, 14, 0),
            rule_name="max_drawdown",
            severity="critical",
        )
        assert event.event_type == "risk_guard_triggered"
        assert event.severity == "critical"
        assert event.details == {}

    def test_with_details(self) -> None:
        event = RiskGuardTriggered(
            timestamp=datetime(2024, 1, 15),
            rule_name="concentration_limit",
            severity="warning",
            details={"current": 0.35, "limit": 0.30},
        )
        assert event.details["current"] == 0.35
