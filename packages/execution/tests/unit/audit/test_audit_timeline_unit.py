"""Tests for normalized execution audit timeline links."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RepairExecutionPayload,
    TradeFillPayload,
)
from ditto_execution.models import (
    AccountSnapshotRecord,
    BrokerEventRecord,
    PositionRecord,
)
from ditto_execution.orders.event import OrderEvent
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.sqlite_journal import SqliteOrderEventJournal
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.trigger import OrderTrigger
from ditto_execution.storage.sqlite.trade import (
    ACCOUNT_SNAPSHOTS_DDL,
    BROKER_EVENTS_DDL,
    POSITIONS_DDL,
    AccountSnapshotWriter,
    BrokerEventWriter,
    PositionWriter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def audit_service(tmp_path: Path) -> Generator[ExecutionAuditService]:
    pool = SQLitePool(str(tmp_path / "test_audit_timeline.db"))
    service = ExecutionAuditService(pool)
    service.init_schema()
    yield service
    pool.close()


@pytest.fixture
def timeline_db(tmp_path: Path) -> Generator[tuple[ExecutionAuditService, Path]]:
    db_path = tmp_path / "test_operating_timeline.db"
    pool = SQLitePool(str(db_path))
    service = ExecutionAuditService(pool)
    service.init_schema()
    yield service, db_path
    pool.close()


def _pre_trade(order_id: str = "ord-001") -> PreTradeDecisionPayload:
    return PreTradeDecisionPayload(
        trade_date="2026-06-01",
        order_id=order_id,
        instrument_id=510300,
        direction="buy",
        original_quantity=1000,
        final_quantity=1000,
        decision="accepted",
        reason=None,
        check_sequence=("lot_size",),
    )


def _fill(
    *,
    order_id: str = "ord-001",
    fill_id: str = "fill-001",
    correlation_id: str | None = "ord-001",
) -> TradeFillPayload:
    return TradeFillPayload(
        trade_date="2026-06-01",
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=510300,
        direction="buy",
        filled_quantity=1000,
        fill_price=4.123,
        fee=5.0,
        slippage=0.002,
        correlation_id=correlation_id,
    )


def _repair(order_id: str = "ord-001") -> RepairExecutionPayload:
    return RepairExecutionPayload(
        trade_date="2026-06-01",
        report_id="rec-001",
        action_id="rec-001:0",
        action_type="import_broker_fill",
        order_id=order_id,
        status="executed",
        message="imported broker fill fill-001",
        effect_count=1,
        correlation_id="rec-001:0",
    )


def _position(
    *,
    snapshot_id: str = "pos-001",
    run_id: str = "run-001",
    quantity: int = 1000,
) -> PositionRecord:
    return PositionRecord(
        snapshot_id=snapshot_id,
        run_id=run_id,
        strategy_id="STRAT-A",
        snapshot_date="2026-06-01",
        instrument_id=510300,
        quantity=quantity,
        available_quantity=0,
        average_cost=4.123,
        market_value=4123.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        total_fees=5.0,
        created_at="2026-06-01T15:00:00+00:00",
    )


def _account_snapshot() -> AccountSnapshotRecord:
    return AccountSnapshotRecord(
        snapshot_id="acct-snap-001",
        run_id="run-001",
        strategy_id="STRAT-A",
        account_id="acct-001",
        snapshot_date="2026-06-01",
        cash_available=95_872.0,
        cash_settled=95_872.0,
        cash_frozen=0.0,
        total_value=99_995.0,
        nav=99_995.0,
        exposure=4_123.0,
        created_at="2026-06-01T15:01:00+00:00",
    )


def _broker_event(
    *,
    event_id: str = "broker-event-001",
    run_id: str = "run-001",
    event_type: str = "order_ack",
    order_id: str = "ord-001",
    broker_order_id: str = "broker-001",
    event_time: str = "2026-06-01T09:31:00+00:00",
) -> BrokerEventRecord:
    return BrokerEventRecord(
        event_id=event_id,
        run_id=run_id,
        broker="paper",
        event_type=event_type,
        event_time=event_time,
        order_id=order_id,
        broker_order_id=broker_order_id,
        fill_id=None,
        instrument_id=510300,
        status="accepted",
        correlation_id=order_id,
        payload={"venue_status": "Accepted"},
        created_at="2026-06-01T09:31:01+00:00",
    )


def _order_event(
    *,
    trigger: OrderTrigger,
    status: OrderStatus,
    timestamp: datetime,
    fill_quantity: int = 0,
) -> OrderEvent:
    return OrderEvent(
        client_id=ClientOrderId(value="ord-001"),
        trigger=trigger,
        status=status,
        fill_price=4.123 if fill_quantity else None,
        fill_quantity=fill_quantity,
        fee=5.0 if fill_quantity else 0.0,
        timestamp=timestamp,
    )


class TestAuditTimelineLinks:
    """Tests for top-level audit correlation columns."""

    def test_query_rows_expose_top_level_link_columns(
        self,
        audit_service: ExecutionAuditService,
    ) -> None:
        audit_service.save_pre_trade_log("run-001", (_pre_trade(),))
        audit_service.save_trade_fill_log("run-001", (_fill(),))

        rows = audit_service.query("run-001")

        pre_trade = rows[0]
        assert pre_trade["order_id"] == "ord-001"
        assert pre_trade["fill_id"] is None
        assert pre_trade["correlation_id"] == "ord-001"

        fill = rows[1]
        assert fill["order_id"] == "ord-001"
        assert fill["fill_id"] == "fill-001"
        assert fill["correlation_id"] == "ord-001"

    def test_query_timeline_filters_by_order_fill_and_correlation(
        self,
        audit_service: ExecutionAuditService,
    ) -> None:
        audit_service.save_pre_trade_log(
            "run-001", (_pre_trade(), _pre_trade("ord-002"))
        )
        audit_service.save_trade_fill_log(
            "run-001",
            (
                _fill(),
                _fill(order_id="ord-002", fill_id="fill-002", correlation_id="ord-002"),
            ),
        )
        audit_service.save_repair_execution_log("run-001", (_repair(),))

        by_order = audit_service.query_timeline("run-001", order_id="ord-001")
        assert [entry.record_type for entry in by_order] == [
            "pre_trade_decision",
            "trade_fill",
            "repair_execution",
        ]
        assert [entry.order_id for entry in by_order] == [
            "ord-001",
            "ord-001",
            "ord-001",
        ]
        assert by_order[1].fill_id == "fill-001"
        assert by_order[2].payload["action_id"] == "rec-001:0"

        by_fill = audit_service.query_timeline("run-001", fill_id="fill-001")
        assert [entry.record_type for entry in by_fill] == ["trade_fill"]

        by_correlation = audit_service.query_timeline(
            "run-001",
            correlation_id="ord-001",
        )
        assert [entry.record_type for entry in by_correlation] == [
            "pre_trade_decision",
            "trade_fill",
        ]

    def test_operating_timeline_includes_order_events_positions_and_accounts(
        self,
        timeline_db: tuple[ExecutionAuditService, Path],
    ) -> None:
        audit_service, db_path = timeline_db
        audit_service.save_pre_trade_log("run-001", (_pre_trade(),))
        audit_service.save_trade_fill_log("run-001", (_fill(),))

        client = SQLiteClient(audit_service._pool)
        client.executescript(POSITIONS_DDL + ACCOUNT_SNAPSHOTS_DDL + BROKER_EVENTS_DDL)
        client.commit()
        PositionWriter(client).save(_position())
        PositionWriter(client).save(
            _position(snapshot_id="pos-002", run_id="run-002", quantity=2000)
        )
        AccountSnapshotWriter(client).save(_account_snapshot())
        BrokerEventWriter(client).save(_broker_event())
        BrokerEventWriter(client).save(
            _broker_event(
                event_id="broker-event-002",
                run_id="run-002",
                event_time="2026-06-01T09:32:00+00:00",
            )
        )

        journal = SqliteOrderEventJournal(db_path=str(db_path))
        journal.append(
            _order_event(
                trigger=OrderTrigger.SUBMIT,
                status=OrderStatus.SUBMITTED,
                timestamp=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            )
        )
        journal.append(
            _order_event(
                trigger=OrderTrigger.FILL,
                status=OrderStatus.FILLED,
                fill_quantity=1000,
                timestamp=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            )
        )
        journal.close()

        timeline = audit_service.query_operating_timeline(
            "run-001",
            strategy_id="STRAT-A",
            order_id="ord-001",
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        assert [entry.record_type for entry in timeline].count("order_event") == 2
        assert "pre_trade_decision" in {entry.record_type for entry in timeline}
        assert "trade_fill" in {entry.record_type for entry in timeline}
        assert "broker_event" in {entry.record_type for entry in timeline}
        assert "position_snapshot" in {entry.record_type for entry in timeline}
        assert "account_snapshot" in {entry.record_type for entry in timeline}

        order_events = [e for e in timeline if e.record_type == "order_event"]
        assert [e.order_id for e in order_events] == ["ord-001", "ord-001"]
        assert [e.payload["trigger"] for e in order_events] == ["submit", "fill"]

        broker_events = [e for e in timeline if e.record_type == "broker_event"]
        assert len(broker_events) == 1
        assert broker_events[0].run_id == "run-001"
        assert broker_events[0].order_id == "ord-001"
        assert broker_events[0].correlation_id == "ord-001"
        assert broker_events[0].payload["event_type"] == "order_ack"
        assert broker_events[0].payload["broker_order_id"] == "broker-001"
        assert broker_events[0].payload["payload"] == {"venue_status": "Accepted"}

        positions = [e for e in timeline if e.record_type == "position_snapshot"]
        assert len(positions) == 1
        assert positions[0].run_id == "run-001"
        assert positions[0].instrument_id == 510300
        assert positions[0].correlation_id == "STRAT-A"
        assert positions[0].payload["snapshot_id"] == "pos-001"
        assert positions[0].payload["run_id"] == "run-001"
        assert positions[0].payload["quantity"] == 1000

        accounts = [e for e in timeline if e.record_type == "account_snapshot"]
        assert len(accounts) == 1
        assert accounts[0].instrument_scope == "account"
        assert accounts[0].correlation_id == "acct-001"
        assert accounts[0].payload["nav"] == pytest.approx(99_995.0)

    def test_operating_timeline_orders_late_replayed_broker_events_by_event_time(
        self,
        timeline_db: tuple[ExecutionAuditService, Path],
    ) -> None:
        audit_service, _ = timeline_db
        client = SQLiteClient(audit_service._pool)
        client.executescript(BROKER_EVENTS_DDL)
        client.commit()
        writer = BrokerEventWriter(client)
        writer.save(
            _broker_event(
                event_id="broker-ack-001",
                event_type="order_ack",
                event_time="2026-06-01T09:30:00+00:00",
            )
        )
        writer.save(
            _broker_event(
                event_id="broker-error-001",
                event_type="fill_query_error",
                event_time="2026-06-01T09:40:00+00:00",
            )
        )
        writer.save(
            BrokerEventRecord(
                event_id="broker-fill-001",
                run_id="run-001",
                broker="paper",
                event_type="fill",
                event_time="2026-06-01T09:31:00+00:00",
                order_id="ord-001",
                broker_order_id="broker-001",
                fill_id="fill-001",
                instrument_id=510300,
                status="partially_filled",
                correlation_id="ord-001",
                payload={"venue_status": "PartiallyFilled"},
                created_at="2026-06-01T10:05:00+00:00",
            )
        )
        writer.save(
            _broker_event(
                event_id="broker-cancel-001",
                event_type="cancel",
                event_time="2026-06-01T10:06:00+00:00",
            )
        )

        timeline = audit_service.query_operating_timeline(
            "run-001",
            order_id="ord-001",
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        broker_events = [
            entry for entry in timeline if entry.record_type == "broker_event"
        ]
        assert [entry.payload["event_type"] for entry in broker_events] == [
            "order_ack",
            "fill",
            "fill_query_error",
            "cancel",
        ]
        assert broker_events[1].created_at == "2026-06-01T09:31:00+00:00"
        assert broker_events[1].payload["created_at"] == "2026-06-01T10:05:00+00:00"

    def test_operating_timeline_filters_broker_events_by_broker_order_id(
        self,
        timeline_db: tuple[ExecutionAuditService, Path],
    ) -> None:
        audit_service, _ = timeline_db
        audit_service.save_pre_trade_log(
            "run-001",
            (_pre_trade(order_id="unrelated-local-order"),),
        )
        client = SQLiteClient(audit_service._pool)
        client.executescript(BROKER_EVENTS_DDL)
        client.commit()
        writer = BrokerEventWriter(client)
        writer.save(
            _broker_event(
                event_id="broker-alpha-ack",
                order_id="ord-alpha",
                broker_order_id="broker-alpha",
                event_type="order_ack",
                event_time="2026-06-01T09:30:00+00:00",
            )
        )
        writer.save(
            _broker_event(
                event_id="broker-beta-ack",
                order_id="ord-beta",
                broker_order_id="broker-beta",
                event_type="order_ack",
                event_time="2026-06-01T09:31:00+00:00",
            )
        )

        timeline = audit_service.query_operating_timeline(
            "run-001",
            broker_order_id="broker-alpha",
            start_date="2026-06-01",
            end_date="2026-06-01",
        )

        broker_events = [
            entry for entry in timeline if entry.record_type == "broker_event"
        ]
        assert [entry.record_type for entry in timeline] == ["broker_event"]
        assert [entry.order_id for entry in broker_events] == ["ord-alpha"]
        assert [entry.payload["broker_order_id"] for entry in broker_events] == [
            "broker-alpha"
        ]
