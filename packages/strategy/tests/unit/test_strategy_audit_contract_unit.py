"""Tests for strategy audit ownership contracts."""

from ditto_strategy.audit import StrategyAuditRecord


def test_strategy_audit_record_captures_decision_trace() -> None:
    record = StrategyAuditRecord(
        audit_id="audit-1",
        strategy_id="trend",
        run_id="run-1",
        event_type="signal_generated",
        occurred_at="2026-05-05T09:30:00Z",
    )

    assert record.event_type == "signal_generated"
    assert record.details == {}
