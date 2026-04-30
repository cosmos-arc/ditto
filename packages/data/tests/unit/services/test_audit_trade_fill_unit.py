"""Tests for trade_fill audit extension.

验证 TradeFillPayload 模型和 ExecutionAuditService.save_trade_fill_log 方法，
包括序列化、空记录处理、查询过滤和 payload 不可变性。
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import FrozenInstanceError

import orjson
import pytest
from ditto_data.models.strategy_audit import AuditRecordType, TradeFillPayload
from ditto_data.services.audit.execution_audit_service import ExecutionAuditService
from ditto_platform.foundation import SQLitePool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_service(tmp_path: object) -> Generator[ExecutionAuditService, None, None]:
    """Create an ExecutionAuditService with a temporary SQLite database."""
    pool = SQLitePool(str(tmp_path / "test_audit_trade_fill.db"))
    service = ExecutionAuditService(pool)
    service.init_schema()
    yield service
    pool.close()


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_trade_fill_payload(
    trade_date: str = "2026-03-20",
    fill_id: str = "FILL-001",
    order_id: str = "ORD-001",
    instrument_id: int = 510300,
    direction: str = "buy",
    filled_quantity: int = 1000,
    fill_price: float = 4.123,
    fee: float = 5.0,
    slippage: float = 0.002,
) -> TradeFillPayload:
    """Create a TradeFillPayload for testing."""
    return TradeFillPayload(
        trade_date=trade_date,
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=instrument_id,
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=slippage,
    )


# ---------------------------------------------------------------------------
# Tests: AuditRecordType.TRADE_FILL
# ---------------------------------------------------------------------------


class TestAuditRecordTypeTradeFill:
    """Tests for TRADE_FILL enum value."""

    def test_trade_fill_value(self) -> None:
        """TRADE_FILL enum value should be 'trade_fill'."""
        assert AuditRecordType.TRADE_FILL == "trade_fill"

    def test_trade_fill_is_str(self) -> None:
        """TRADE_FILL should be a string (StrEnum)."""
        assert isinstance(AuditRecordType.TRADE_FILL, str)


# ---------------------------------------------------------------------------
# Tests: TradeFillPayload
# ---------------------------------------------------------------------------


class TestTradeFillPayload:
    """Tests for TradeFillPayload dataclass."""

    def test_is_frozen(self) -> None:
        """TradeFillPayload should be frozen (immutable)."""
        payload = _make_trade_fill_payload()
        with pytest.raises(FrozenInstanceError):
            payload.fill_id = "FILL-CHANGED"  # type: ignore[misc]

    def test_field_values(self) -> None:
        """TradeFillPayload should store all field values correctly."""
        payload = _make_trade_fill_payload(
            trade_date="2026-04-01",
            fill_id="FILL-002",
            order_id="ORD-002",
            instrument_id=159915,
            direction="sell",
            filled_quantity=500,
            fill_price=1.234,
            fee=2.5,
            slippage=0.001,
        )
        assert payload.trade_date == "2026-04-01"
        assert payload.fill_id == "FILL-002"
        assert payload.order_id == "ORD-002"
        assert payload.instrument_id == 159915
        assert payload.direction == "sell"
        assert payload.filled_quantity == 500
        assert payload.fill_price == 1.234
        assert payload.fee == 2.5
        assert payload.slippage == 0.001


# ---------------------------------------------------------------------------
# Tests: save_trade_fill_log
# ---------------------------------------------------------------------------


class TestSaveTradeFillLog:
    """Tests for ExecutionAuditService.save_trade_fill_log()."""

    def test_saves_single_record(self, audit_service: ExecutionAuditService) -> None:
        """save_trade_fill_log should insert one record and return count 1."""
        rec = _make_trade_fill_payload()
        count = audit_service.save_trade_fill_log("run-001", (rec,))

        assert count == 1
        rows = audit_service.query("run-001")
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-001"
        assert rows[0]["trade_date"] == "2026-03-20"
        assert rows[0]["record_type"] == "trade_fill"
        assert rows[0]["instrument_id"] == 510300
        assert rows[0]["instrument_scope"] == "instrument"

    def test_saves_multiple_records(self, audit_service: ExecutionAuditService) -> None:
        """save_trade_fill_log should insert multiple records and return count."""
        rec1 = _make_trade_fill_payload(trade_date="2026-03-20", fill_id="FILL-001")
        rec2 = _make_trade_fill_payload(trade_date="2026-03-21", fill_id="FILL-002")
        count = audit_service.save_trade_fill_log("run-001", (rec1, rec2))

        assert count == 2
        rows = audit_service.query("run-001", record_type="trade_fill")
        assert len(rows) == 2

    def test_serializes_payload_with_orjson(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """Payload should be orjson-serialized dict of the record fields."""
        rec = _make_trade_fill_payload()
        audit_service.save_trade_fill_log("run-001", (rec,))

        rows = audit_service.query("run-001", record_type="trade_fill")
        payload = orjson.loads(rows[0]["payload"])
        assert payload["trade_date"] == "2026-03-20"
        assert payload["fill_id"] == "FILL-001"
        assert payload["order_id"] == "ORD-001"
        assert payload["instrument_id"] == 510300
        assert payload["direction"] == "buy"
        assert payload["filled_quantity"] == 1000
        assert payload["fill_price"] == 4.123
        assert payload["fee"] == 5.0
        assert payload["slippage"] == 0.002

    def test_empty_tuple_returns_zero(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """save_trade_fill_log with empty tuple should return 0."""
        count = audit_service.save_trade_fill_log("run-001", ())
        assert count == 0

    def test_different_run_ids_isolated(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """Records saved under different run_ids should not mix."""
        rec = _make_trade_fill_payload()
        audit_service.save_trade_fill_log("run-A", (rec,))
        audit_service.save_trade_fill_log("run-B", (rec,))

        assert len(audit_service.query("run-A")) == 1
        assert len(audit_service.query("run-B")) == 1


# ---------------------------------------------------------------------------
# Tests: query with trade_fill type
# ---------------------------------------------------------------------------


class TestQueryTradeFill:
    """Tests for query() filtering by trade_fill record type."""

    def test_query_by_record_type_trade_fill(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query with record_type='trade_fill' should filter correctly."""
        rec = _make_trade_fill_payload()
        audit_service.save_trade_fill_log("run-001", (rec,))

        rows = audit_service.query("run-001", record_type="trade_fill")
        assert len(rows) == 1
        assert rows[0]["record_type"] == "trade_fill"

    def test_query_trade_fill_excludes_other_types(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query for trade_fill should not return risk_scan or pre_trade records."""
        from ditto_data.models.strategy_audit import (
            PreTradeDecisionPayload,
            RiskScanPayload,
            RiskScope,
        )

        risk = RiskScanPayload(
            trade_date="2026-03-20",
            rule_id="test",
            instrument_id=510300,
            scope=RiskScope.INSTRUMENT,
            severity="warning",
            action_taken="alert",
            detail="test",
            current_value=0.1,
            threshold=0.1,
        )
        pre_trade = PreTradeDecisionPayload(
            trade_date="2026-03-20",
            order_id="ORD-001",
            instrument_id=510300,
            direction="buy",
            original_quantity=1000,
            final_quantity=1000,
            decision="accepted",
            reason=None,
        )
        fill = _make_trade_fill_payload()

        audit_service.save_risk_log("run-001", (risk,))
        audit_service.save_pre_trade_log("run-001", (pre_trade,))
        audit_service.save_trade_fill_log("run-001", (fill,))

        # Total 3 records
        all_rows = audit_service.query("run-001")
        assert len(all_rows) == 3

        # Only trade_fill
        fill_rows = audit_service.query("run-001", record_type="trade_fill")
        assert len(fill_rows) == 1
        assert fill_rows[0]["record_type"] == "trade_fill"

    def test_query_trade_fill_with_date_range(
        self, audit_service: ExecutionAuditService
    ) -> None:
        """query trade_fill records with date range filter."""
        rec1 = _make_trade_fill_payload(trade_date="2026-03-18", fill_id="F1")
        rec2 = _make_trade_fill_payload(trade_date="2026-03-20", fill_id="F2")
        rec3 = _make_trade_fill_payload(trade_date="2026-03-22", fill_id="F3")
        audit_service.save_trade_fill_log("run-001", (rec1, rec2, rec3))

        rows = audit_service.query(
            "run-001",
            record_type="trade_fill",
            start_date="2026-03-19",
            end_date="2026-03-21",
        )
        assert len(rows) == 1
        assert rows[0]["trade_date"] == "2026-03-20"
