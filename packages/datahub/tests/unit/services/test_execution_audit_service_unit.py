"""Tests for ExecutionAuditService — SQLite audit log persistence.

使用 DataHub 本地 DTO (RiskScanPayload / PreTradeDecisionPayload)，
不再依赖 Core 审计记录类型。
"""

from __future__ import annotations

from collections.abc import Generator

import orjson
import pytest
from ditto_datahub.models.strategy_audit import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)
from ditto_datahub.services.audit.execution_audit_service import ExecutionAuditService
from ditto_infra.foundation import SQLitePool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_service(tmp_path: object) -> Generator[ExecutionAuditService, None, None]:
    """Create an ExecutionAuditService with a temporary SQLite database."""
    pool = SQLitePool(str(tmp_path / "test_audit.db"))
    service = ExecutionAuditService(pool)
    service.init_schema()
    yield service
    pool.close()


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_risk_payload(
    trade_date: str = "2026-03-20",
    rule_id: str = "max_drawdown",
    instrument_id: str = "510300.SH",
    severity: str = "warning",
    action_taken: str = "alert",
) -> RiskScanPayload:
    """Create a RiskScanPayload for testing."""
    return RiskScanPayload(
        trade_date=trade_date,
        rule_id=rule_id,
        instrument_id=instrument_id,
        severity=severity,
        action_taken=action_taken,
        detail="组合回撤 12.00% 超过警告阈值 10.00%",
        current_value=0.12,
        threshold=0.10,
    )


def _make_pre_trade_payload(
    trade_date: str = "2026-03-20",
    order_id: str = "ORD-001",
    instrument_id: str = "510300.SH",
    direction: str = "buy",
    decision: str = "accepted",
) -> PreTradeDecisionPayload:
    """Create a PreTradeDecisionPayload for testing."""
    return PreTradeDecisionPayload(
        trade_date=trade_date,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        original_quantity=1000,
        final_quantity=1000,
        decision=decision,
        reason=None,
        check_sequence=("lot_size", "buying_power"),
    )


# ---------------------------------------------------------------------------
# Tests: init_schema
# ---------------------------------------------------------------------------


class TestInitSchema:
    """Tests for init_schema()."""

    def test_creates_execution_audit_table(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """init_schema should create the execution_audit table."""
        conn = audit_service._pool.get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='execution_audit'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "execution_audit"

    def test_creates_indexes(self, audit_service: ExecutionAuditService) -> None:
        """init_schema should create the expected indexes."""
        conn = audit_service._pool.get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_audit_%'"
        )
        index_names = {row[0] for row in cursor.fetchall()}
        assert "idx_audit_run_date" in index_names
        assert "idx_audit_run_type" in index_names

    def test_idempotent(self, audit_service: ExecutionAuditService) -> None:
        """Calling init_schema twice should not raise."""
        audit_service.init_schema()  # second call
        conn = audit_service._pool.get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM execution_audit")
        assert cursor.fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Tests: save_risk_log
# ---------------------------------------------------------------------------


class TestSaveRiskLog:
    """Tests for save_risk_log()."""

    def test_saves_single_record(self, audit_service: ExecutionAuditService) -> None:
        """save_risk_log should insert one record and return count 1."""
        rec = _make_risk_payload()
        count = audit_service.save_risk_log("run-001", (rec,))

        assert count == 1
        rows = audit_service.query("run-001")
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-001"
        assert rows[0]["trade_date"] == "2026-03-20"
        assert rows[0]["record_type"] == "risk_scan"
        assert rows[0]["instrument_id"] == "510300.SH"

    def test_saves_multiple_records(self, audit_service: ExecutionAuditService) -> None:
        """save_risk_log should insert multiple records and return count."""
        rec1 = _make_risk_payload(trade_date="2026-03-20", rule_id="max_drawdown")
        rec2 = _make_risk_payload(
            trade_date="2026-03-21", rule_id="concentration_limit"
        )
        count = audit_service.save_risk_log("run-001", (rec1, rec2))

        assert count == 2
        rows = audit_service.query("run-001", record_type="risk_scan")
        assert len(rows) == 2

    def test_serializes_payload_with_orjson(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """Payload should be orjson-serialized dict of the record fields."""
        rec = _make_risk_payload()
        audit_service.save_risk_log("run-001", (rec,))

        rows = audit_service.query("run-001")
        payload = orjson.loads(rows[0]["payload"])
        assert payload["trade_date"] == "2026-03-20"
        assert payload["rule_id"] == "max_drawdown"
        assert payload["severity"] == "warning"
        assert payload["action_taken"] == "alert"

    def test_empty_tuple_returns_zero(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """save_risk_log with empty tuple should return 0 without error."""
        count = audit_service.save_risk_log("run-001", ())
        assert count == 0

    def test_different_run_ids_isolated(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """Records saved under different run_ids should not mix."""
        rec = _make_risk_payload()
        audit_service.save_risk_log("run-A", (rec,))
        audit_service.save_risk_log("run-B", (rec,))

        assert len(audit_service.query("run-A")) == 1
        assert len(audit_service.query("run-B")) == 1


# ---------------------------------------------------------------------------
# Tests: save_pre_trade_log
# ---------------------------------------------------------------------------


class TestSavePreTradeLog:
    """Tests for save_pre_trade_log()."""

    def test_saves_single_record(self, audit_service: ExecutionAuditService) -> None:
        """save_pre_trade_log should insert one record and return count 1."""
        rec = _make_pre_trade_payload()
        count = audit_service.save_pre_trade_log("run-001", (rec,))

        assert count == 1
        rows = audit_service.query("run-001", record_type="pre_trade_decision")
        assert len(rows) == 1
        assert rows[0]["record_type"] == "pre_trade_decision"
        assert rows[0]["instrument_id"] == "510300.SH"

    def test_serializes_payload_with_orjson(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """Payload should be orjson-serialized dict of the record fields."""
        rec = _make_pre_trade_payload()
        audit_service.save_pre_trade_log("run-001", (rec,))

        rows = audit_service.query("run-001", record_type="pre_trade_decision")
        payload = orjson.loads(rows[0]["payload"])
        assert payload["trade_date"] == "2026-03-20"
        assert payload["order_id"] == "ORD-001"
        assert payload["direction"] == "buy"
        assert payload["decision"] == "accepted"
        assert payload["check_sequence"] == ["lot_size", "buying_power"]

    def test_empty_tuple_returns_zero(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """save_pre_trade_log with empty tuple should return 0."""
        count = audit_service.save_pre_trade_log("run-001", ())
        assert count == 0

    def test_saves_rejected_record(self, audit_service: ExecutionAuditService) -> None:
        """save_pre_trade_log should handle rejected decisions (final_quantity=0)."""
        rec = PreTradeDecisionPayload(
            trade_date="2026-03-20",
            order_id="ORD-REJ",
            instrument_id="159915.SZ",
            direction="buy",
            original_quantity=500,
            final_quantity=0,
            decision="rejected",
            reason="insufficient buying power",
            check_sequence=("buying_power",),
        )
        count = audit_service.save_pre_trade_log("run-001", (rec,))
        assert count == 1

        rows = audit_service.query("run-001", record_type="pre_trade_decision")
        payload = orjson.loads(rows[0]["payload"])
        assert payload["decision"] == "rejected"
        assert payload["final_quantity"] == 0
        assert payload["reason"] == "insufficient buying power"


# ---------------------------------------------------------------------------
# Tests: query
# ---------------------------------------------------------------------------


class TestQuery:
    """Tests for query() with various filters."""

    def _seed_data(self, svc: ExecutionAuditService) -> None:
        """Insert sample data across run_ids, dates, and types."""
        risk1 = _make_risk_payload(trade_date="2026-03-18", rule_id="max_drawdown")
        risk2 = _make_risk_payload(
            trade_date="2026-03-20", rule_id="concentration_limit"
        )
        risk3 = _make_risk_payload(trade_date="2026-03-22", rule_id="max_drawdown")

        pt1 = _make_pre_trade_payload(trade_date="2026-03-18", order_id="ORD-001")
        pt2 = _make_pre_trade_payload(trade_date="2026-03-20", order_id="ORD-002")
        pt3 = _make_pre_trade_payload(trade_date="2026-03-22", order_id="ORD-003")

        svc.save_risk_log("run-A", (risk1, risk2, risk3))
        svc.save_pre_trade_log("run-A", (pt1, pt2, pt3))
        svc.save_risk_log("run-B", (risk2,))

    def test_query_by_run_id(self, audit_service: ExecutionAuditService) -> None:
        """query with only run_id should return all records for that run."""
        self._seed_data(audit_service)

        rows_a = audit_service.query("run-A")
        rows_b = audit_service.query("run-B")

        assert len(rows_a) == 6  # 3 risk + 3 pre-trade
        assert len(rows_b) == 1

    def test_query_by_record_type_risk_scan(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with record_type='risk_scan' should filter correctly."""
        self._seed_data(audit_service)

        rows = audit_service.query("run-A", record_type="risk_scan")
        assert len(rows) == 3
        assert all(r["record_type"] == "risk_scan" for r in rows)

    def test_query_by_record_type_pre_trade(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with record_type='pre_trade_decision' should filter correctly."""
        self._seed_data(audit_service)

        rows = audit_service.query("run-A", record_type="pre_trade_decision")
        assert len(rows) == 3
        assert all(r["record_type"] == "pre_trade_decision" for r in rows)

    def test_query_by_date_range(self, audit_service: ExecutionAuditService) -> None:
        """query with start_date/end_date should filter by trade_date."""
        self._seed_data(audit_service)

        rows = audit_service.query(
            "run-A", start_date="2026-03-19", end_date="2026-03-21"
        )
        # Only date 2026-03-20 falls in [19, 21]; 1 risk + 1 pre-trade = 2 rows
        assert len(rows) == 2
        dates = {r["trade_date"] for r in rows}
        assert dates == {"2026-03-20"}

    def test_query_by_start_date_only(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with only start_date should include dates >= start_date."""
        self._seed_data(audit_service)

        rows = audit_service.query("run-A", start_date="2026-03-20")
        # Dates 20 and 22 match; 2 records each = 4 rows
        assert len(rows) == 4
        for r in rows:
            assert r["trade_date"] >= "2026-03-20"

    def test_query_by_end_date_only(self, audit_service: ExecutionAuditService) -> None:
        """query with only end_date should include dates <= end_date."""
        self._seed_data(audit_service)

        rows = audit_service.query("run-A", end_date="2026-03-20")
        # Dates 18 and 20 match; 2 records each = 4 rows
        assert len(rows) == 4
        for r in rows:
            assert r["trade_date"] <= "2026-03-20"

    def test_query_combined_filters(self, audit_service: ExecutionAuditService) -> None:
        """query with all filters combined should apply all conditions."""
        self._seed_data(audit_service)

        rows = audit_service.query(
            "run-A",
            record_type="risk_scan",
            start_date="2026-03-19",
            end_date="2026-03-21",
        )
        assert len(rows) == 1
        assert rows[0]["record_type"] == "risk_scan"
        assert rows[0]["trade_date"] == "2026-03-20"

    def test_query_nonexistent_run_id_returns_empty(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query for a non-existent run_id should return empty list."""
        rows = audit_service.query("nonexistent-run")
        assert rows == []

    def test_query_returns_dicts_with_expected_keys(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query result rows should contain all table columns."""
        rec = _make_risk_payload()
        audit_service.save_risk_log("run-001", (rec,))

        rows = audit_service.query("run-001")
        row = rows[0]
        expected_keys = {
            "id",
            "run_id",
            "trade_date",
            "record_type",
            "instrument_id",
            "payload",
            "created_at",
        }
        assert set(row.keys()) == expected_keys

    def test_query_ordered_by_trade_date_and_id(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query results should be ordered by trade_date ASC, id ASC."""
        risk1 = _make_risk_payload(trade_date="2026-03-22")
        risk2 = _make_risk_payload(trade_date="2026-03-20")
        risk3 = _make_risk_payload(trade_date="2026-03-18")
        # Insert in non-chronological order
        audit_service.save_risk_log("run-001", (risk1, risk2, risk3))

        rows = audit_service.query("run-001")
        assert rows[0]["trade_date"] == "2026-03-18"
        assert rows[1]["trade_date"] == "2026-03-20"
        assert rows[2]["trade_date"] == "2026-03-22"

    def test_query_no_match_with_wrong_type(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with record_type that has no matching records returns empty."""
        audit_service.save_risk_log("run-001", (_make_risk_payload(),))

        rows = audit_service.query("run-001", record_type="pre_trade_decision")
        assert rows == []

    def test_query_date_range_no_overlap(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with date range that doesn't overlap data returns empty."""
        audit_service.save_risk_log(
            "run-001",
            (_make_risk_payload(trade_date="2026-03-20"),),
        )

        rows = audit_service.query(
            "run-001", start_date="2026-04-01", end_date="2026-04-30"
        )
        assert rows == []
