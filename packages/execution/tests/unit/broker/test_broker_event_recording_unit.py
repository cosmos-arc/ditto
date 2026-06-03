"""BrokerGateway broker-event recording conformance tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_execution.broker.recording import BrokerEventRecordingGateway
from ditto_execution.models import BrokerEventRecord
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import Account, AccountView


class InMemoryBrokerEventSink:
    """Small in-memory stand-in for BrokerEventDataPort."""

    def __init__(self) -> None:
        self._records: dict[str, BrokerEventRecord] = {}

    def save_broker_event(self, record: BrokerEventRecord) -> None:
        self._records[record.event_id] = record

    def list_broker_events(
        self,
        run_id: str,
        *,
        event_type: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        fill_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[BrokerEventRecord]:
        del broker_order_id, start_date, end_date
        records = [
            record for record in self._records.values() if record.run_id == run_id
        ]
        if event_type is not None:
            records = [record for record in records if record.event_type == event_type]
        if order_id is not None:
            records = [record for record in records if record.order_id == order_id]
        if fill_id is not None:
            records = [record for record in records if record.fill_id == fill_id]
        return sorted(records, key=lambda record: (record.event_time, record.event_id))


class ManualBrokerGateway:
    """Controllable gateway used to verify non-fill event recording."""

    def __init__(self) -> None:
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def get_account(self) -> AccountView:
        return Account().get_view()

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(order=order, status=OrderStatus.SUBMITTED)

    def cancel_order(self, order_id: str) -> bool:
        return order_id == "cancel-ok"

    def reject_order(self, order_id: str, reason: str) -> bool:
        return order_id == "reject-ok" and reason == "risk limit"

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        del order_id
        return ()


class ReplayBrokerGateway(ManualBrokerGateway):
    """Gateway fixture that exposes replayed broker fills."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(order=order, status=OrderStatus.SUBMITTED)

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        return (
            FillEvent(
                fill_id="broker-fill-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=40,
                fill_price=10.0,
                fee=0.0,
                slippage=0.0,
                event_time=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                cumulative_quantity=40,
                leaves_quantity=60,
            ),
            FillEvent(
                fill_id="broker-fill-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=40,
                fill_price=10.0,
                fee=0.0,
                slippage=0.0,
                event_time=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                cumulative_quantity=40,
                leaves_quantity=60,
            ),
        )


class BrokerAckIdGateway(ReplayBrokerGateway):
    """Gateway fixture whose submit ack includes the broker-side order ID."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )


class BlankBrokerAckIdGateway(ReplayBrokerGateway):
    """Gateway fixture whose submit ack carries a blank broker order ID."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id="   ",
        )


class BrokerAckNoFillGateway(ManualBrokerGateway):
    """Gateway fixture whose ack carries broker order ID before fills arrive."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )


class ReconnectedReplayBrokerGateway(ReplayBrokerGateway):
    """Gateway fixture that replays broker callbacks after wrapper recreation."""

    def cancel_order(self, order_id: str) -> bool:
        return order_id == "live-reconnect-001"


class OrderScopedFillIdBrokerGateway(ManualBrokerGateway):
    """Gateway fixture whose broker fill IDs are only unique per order."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(order=order, status=OrderStatus.SUBMITTED)

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        return (
            FillEvent(
                fill_id="broker-fill-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=100,
                fill_price=10.0,
                fee=0.0,
                slippage=0.0,
                event_time=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                cumulative_quantity=100,
                leaves_quantity=0,
            ),
        )


class ProgressiveFillReplayBrokerGateway(ManualBrokerGateway):
    """Gateway fixture that replays the same fill ID with later progress."""

    def __init__(self) -> None:
        super().__init__()
        self._query_count = 0

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        self._query_count += 1
        if self._query_count == 1:
            return (
                FillEvent(
                    fill_id="broker-fill-progress-001",
                    order_id=order_id,
                    instrument_id=InstrumentId(510300),
                    direction=OrderSide.BUY,
                    filled_quantity=40,
                    fill_price=10.0,
                    fee=0.0,
                    slippage=0.0,
                    event_time=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                    cumulative_quantity=40,
                    leaves_quantity=60,
                ),
            )
        return (
            FillEvent(
                fill_id="broker-fill-progress-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=60,
                fill_price=10.1,
                fee=0.0,
                slippage=0.0,
                event_time=datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
                cumulative_quantity=100,
                leaves_quantity=0,
            ),
        )


class CorrectedFillReplayBrokerGateway(ManualBrokerGateway):
    """Gateway fixture that replays the same fill progress with revised economics."""

    def __init__(self) -> None:
        super().__init__()
        self._query_count = 0

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        self._query_count += 1
        if self._query_count == 1:
            fill_price = 10.0
            fee = 1.0
            event_time = datetime(2026, 6, 1, 9, 31, tzinfo=UTC)
        else:
            fill_price = 10.05
            fee = 1.1
            event_time = datetime(2026, 6, 1, 9, 32, tzinfo=UTC)
        return (
            FillEvent(
                fill_id="broker-fill-corrected-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=100,
                fill_price=fill_price,
                fee=fee,
                slippage=0.0,
                event_time=event_time,
                cumulative_quantity=100,
                leaves_quantity=0,
            ),
        )


class CorrectedBrokerOrderLinkReplayGateway(ManualBrokerGateway):
    """Gateway fixture that replays the same fill after broker-order ID correction."""

    def __init__(self) -> None:
        super().__init__()
        self._submit_count = 0

    def submit_order(self, order: Order) -> OrderTicket:
        self._submit_count += 1
        prefix = "broker-old" if self._submit_count == 1 else "broker-new"
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"{prefix}-{order.order_id}",
        )

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        return (
            FillEvent(
                fill_id="broker-fill-link-001",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=100,
                fill_price=10.0,
                fee=0.0,
                slippage=0.0,
                event_time=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                cumulative_quantity=100,
                leaves_quantity=0,
            ),
        )


class FillQueryFailingBrokerGateway(ManualBrokerGateway):
    """Gateway fixture whose order submit succeeds but fill polling fails."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(order=order, status=OrderStatus.SUBMITTED)

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        raise RuntimeError(f"fill query unavailable for {order_id}")


class ResponseFailingBrokerGateway(ManualBrokerGateway):
    """Gateway fixture whose broker response calls fail before returning a result."""

    def cancel_order(self, order_id: str) -> bool:
        raise RuntimeError(f"cancel transport unavailable for {order_id}")

    def reject_order(self, order_id: str, reason: str) -> bool:
        del reason
        raise RuntimeError(f"reject transport unavailable for {order_id}")


def _fixed_now() -> datetime:
    return datetime(2026, 6, 1, 9, 30, tzinfo=UTC)


class SequenceClock:
    """Deterministic clock that advances once per call."""

    def __init__(self, *values: datetime) -> None:
        self._values = list(values)

    def __call__(self) -> datetime:
        if not self._values:
            raise AssertionError("clock exhausted")
        return self._values.pop(0)


def _order(
    cid: str = "ord-001",
    *,
    quantity: int = 100,
    price: float = 10.0,
) -> Order:
    return Order(
        client_id=ClientOrderId(value=cid),
        instrument_id=InstrumentId(510300),
        order_type=OrderType.LIMIT,
        direction=OrderSide.BUY,
        quantity=quantity,
        price=price,
    )


def test_submit_records_ack_and_immediate_fill_events() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=PaperBrokerGateway(initial_cash=100_000.0),
        event_sink=sink,
        run_id="run-001",
        broker="paper",
        now=_fixed_now,
    )

    gateway.submit_order(_order())

    events = sink.list_broker_events("run-001")
    assert {event.event_type for event in events} == {"order_ack", "fill"}

    ack = next(event for event in events if event.event_type == "order_ack")
    assert ack.event_id == "run-001:paper:order_ack:ord-001:filled"
    assert ack.order_id == "ord-001"
    assert ack.instrument_id == 510300
    assert ack.status == "filled"
    assert ack.correlation_id == "ord-001"
    assert ack.event_time == "2026-06-01T09:30:00+00:00"
    assert ack.payload["quantity"] == 100
    assert ack.payload["leaves_quantity"] == 0

    fill = next(event for event in events if event.event_type == "fill")
    assert fill.event_id.startswith("run-001:paper:fill:ord-001:paper-")
    assert fill.order_id == "ord-001"
    assert fill.fill_id is not None
    assert fill.instrument_id == 510300
    assert fill.status == "filled"
    assert fill.correlation_id == "ord-001"
    assert fill.payload["filled_quantity"] == 100
    assert fill.payload["cumulative_quantity"] == 100
    assert fill.payload["leaves_quantity"] == 0


def test_query_fills_records_fill_events_with_deterministic_ids() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=PaperBrokerGateway(initial_cash=100_000.0),
        event_sink=sink,
        run_id="run-001",
        broker="paper",
        now=_fixed_now,
    )

    gateway.submit_order(_order("ord-002"))
    fills = gateway.query_fills("ord-002")
    gateway.query_fills("ord-002")

    fill_events = sink.list_broker_events("run-001", event_type="fill")
    assert len(fill_events) == 1
    assert fill_events[0].event_id == (
        f"run-001:paper:fill:ord-002:{fills[0].fill_id}:"
        f"{fills[0].cumulative_quantity}:{fills[0].leaves_quantity}"
    )


def test_get_account_records_account_update_event() -> None:
    from ditto_execution.broker.gateways.paper import PaperBrokerGateway

    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=PaperBrokerGateway(initial_cash=100_000.0),
        event_sink=sink,
        run_id="run-account-001",
        broker="paper",
        now=_fixed_now,
    )

    view = gateway.get_account()

    events = sink.list_broker_events("run-account-001", event_type="account_update")
    assert len(events) == 1
    event = events[0]
    assert event.event_id == (
        "run-account-001:paper:account_update:2026-06-01T09:30:00+00:00"
    )
    assert event.status == "snapshot"
    assert event.correlation_id == "run-account-001"
    assert event.event_time == "2026-06-01T09:30:00+00:00"
    assert event.payload == {
        "cash_available": view.cash.available,
        "cash_settled": view.cash.settled,
        "cash_frozen": view.cash.frozen,
        "cash_total": view.cash.total,
        "total_value": view.total_value,
        "nav": view.nav,
        "exposure": view.exposure,
        "position_count": 0,
    }


def test_connect_cancel_and_reject_results_are_recorded() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-002",
        broker="manual",
        now=_fixed_now,
    )

    gateway.connect()
    gateway.cancel_order("cancel-ok")
    gateway.cancel_order("cancel-missing")
    gateway.reject_order("reject-ok", "risk limit")

    events = sink.list_broker_events("run-002")
    assert [(event.event_type, event.order_id, event.status) for event in events] == [
        ("cancel", "cancel-missing", "rejected"),
        ("cancel", "cancel-ok", "accepted"),
        ("connect", None, "connected"),
        ("reject", "reject-ok", "rejected"),
    ]
    assert events[0].payload["accepted"] is False
    assert events[1].payload["accepted"] is True
    assert events[3].payload["reason"] == "risk limit"


def test_reconnect_records_each_connect_attempt_as_distinct_event() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-001",
        broker="manual",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
            datetime(2026, 6, 1, 10, 5, 1, tzinfo=UTC),
        ),
    )

    gateway.connect()
    gateway.connect()

    events = sink.list_broker_events("run-reconnect-001", event_type="connect")
    assert [event.event_time for event in events] == [
        "2026-06-01T09:30:00+00:00",
        "2026-06-01T10:05:00+00:00",
    ]
    assert [event.event_id for event in events] == [
        "run-reconnect-001:manual:connect:2026-06-01T09:30:00+00:00",
        "run-reconnect-001:manual:connect:2026-06-01T10:05:00+00:00",
    ]


def test_repeated_cancel_attempts_are_recorded_as_distinct_responses() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-cancel-retry-001",
        broker="manual",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        ),
    )

    gateway.cancel_order("cancel-ok")
    gateway.cancel_order("cancel-ok")

    events = sink.list_broker_events("run-cancel-retry-001", event_type="cancel")
    assert [event.event_id for event in events] == [
        "run-cancel-retry-001:manual:cancel:cancel-ok:accepted:"
        "2026-06-01T09:30:00+00:00",
        "run-cancel-retry-001:manual:cancel:cancel-ok:accepted:"
        "2026-06-01T09:31:00+00:00",
    ]
    assert [(event.order_id, event.status) for event in events] == [
        ("cancel-ok", "accepted"),
        ("cancel-ok", "accepted"),
    ]


def test_event_time_collisions_do_not_collapse_lifecycle_or_response_events() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-time-collision-001",
        broker="manual",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 2, tzinfo=UTC),
        ),
    )

    gateway.connect()
    gateway.connect()
    gateway.cancel_order("cancel-ok")
    gateway.cancel_order("cancel-ok")

    connect_events = sink.list_broker_events(
        "run-time-collision-001",
        event_type="connect",
    )
    cancel_events = sink.list_broker_events(
        "run-time-collision-001",
        event_type="cancel",
    )
    assert [event.event_id for event in connect_events] == [
        "run-time-collision-001:manual:connect:2026-06-01T09:30:00+00:00",
        "run-time-collision-001:manual:connect:2026-06-01T09:30:00+00:00:attempt-2",
    ]
    assert [event.created_at for event in connect_events] == [
        "2026-06-01T09:30:01+00:00",
        "2026-06-01T09:30:02+00:00",
    ]
    assert [event.event_id for event in cancel_events] == [
        "run-time-collision-001:manual:cancel:cancel-ok:accepted:"
        "2026-06-01T09:31:00+00:00",
        "run-time-collision-001:manual:cancel:cancel-ok:accepted:"
        "2026-06-01T09:31:00+00:00:attempt-2",
    ]
    assert [event.created_at for event in cancel_events] == [
        "2026-06-01T09:31:01+00:00",
        "2026-06-01T09:31:02+00:00",
    ]


def test_repeated_reject_attempts_are_recorded_as_distinct_responses() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-reject-retry-001",
        broker="manual",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 40, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 40, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 41, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 41, 1, tzinfo=UTC),
        ),
    )

    gateway.reject_order("reject-ok", "risk limit")
    gateway.reject_order("reject-ok", "risk limit")

    events = sink.list_broker_events("run-reject-retry-001", event_type="reject")
    assert [event.event_id for event in events] == [
        "run-reject-retry-001:manual:reject:reject-ok:rejected:"
        "2026-06-01T09:40:00+00:00",
        "run-reject-retry-001:manual:reject:reject-ok:rejected:"
        "2026-06-01T09:41:00+00:00",
    ]
    assert [
        (event.order_id, event.status, event.payload["reason"]) for event in events
    ] == [
        ("reject-ok", "rejected", "risk limit"),
        ("reject-ok", "rejected", "risk limit"),
    ]


def test_broker_order_id_lookup_links_ack_fill_and_cancel_events() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-live-001",
        broker="live-sim",
        now=_fixed_now,
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    gateway.submit_order(_order("live-001"))
    gateway.query_fills("live-001")
    gateway.cancel_order("live-001")

    events = sink.list_broker_events("run-live-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["order_ack"].broker_order_id == "broker-live-001"
    assert by_type["order_ack"].payload["broker_order_id"] == "broker-live-001"
    assert by_type["fill"].broker_order_id == "broker-live-001"
    assert by_type["fill"].payload["broker_order_id"] == "broker-live-001"
    assert by_type["cancel"].broker_order_id == "broker-live-001"
    assert by_type["cancel"].payload["broker_order_id"] == "broker-live-001"

    fill_events = sink.list_broker_events("run-live-001", event_type="fill")
    assert len(fill_events) == 1
    assert fill_events[0].event_id == (
        "run-live-001:live-sim:fill:live-001:broker-fill-001:40:60"
    )


def test_submit_extracts_broker_order_id_from_ticket_ack() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-live-ack-001",
        broker="live-sim",
        now=_fixed_now,
    )

    gateway.submit_order(_order("live-ack-001"))

    ack = next(
        event
        for event in sink.list_broker_events(
            "run-live-ack-001",
            event_type="order_ack",
        )
    )
    assert ack.broker_order_id == "broker-live-ack-001"
    assert ack.payload["broker_order_id"] == "broker-live-ack-001"


def test_blank_ticket_broker_order_id_uses_lookup_link() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BlankBrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-live-blank-ack-001",
        broker="live-sim",
        now=_fixed_now,
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    gateway.submit_order(_order("live-blank-ack-001"))
    gateway.cancel_order("live-blank-ack-001")

    events = sink.list_broker_events("run-live-blank-ack-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["order_ack"].broker_order_id == "broker-live-blank-ack-001"
    assert by_type["order_ack"].payload["broker_order_id"] == (
        "broker-live-blank-ack-001"
    )
    assert by_type["fill"].broker_order_id == "broker-live-blank-ack-001"
    assert by_type["fill"].payload["broker_order_id"] == "broker-live-blank-ack-001"
    assert by_type["cancel"].broker_order_id == "broker-live-blank-ack-001"
    assert by_type["cancel"].payload["broker_order_id"] == ("broker-live-blank-ack-001")


def test_ticket_broker_order_id_links_follow_up_fill_and_cancel_events() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-live-ack-002",
        broker="live-sim",
        now=_fixed_now,
    )

    gateway.submit_order(_order("live-ack-002"))
    gateway.query_fills("live-ack-002")
    gateway.cancel_order("live-ack-002")

    events = sink.list_broker_events("run-live-ack-002")
    by_type = {event.event_type: event for event in events}
    assert by_type["order_ack"].broker_order_id == "broker-live-ack-002"
    assert by_type["fill"].broker_order_id == "broker-live-ack-002"
    assert by_type["fill"].payload["broker_order_id"] == "broker-live-ack-002"
    assert by_type["cancel"].broker_order_id == "broker-live-ack-002"
    assert by_type["cancel"].payload["broker_order_id"] == "broker-live-ack-002"


def test_repeated_order_ack_callbacks_are_recorded_as_distinct_attempts() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
    )
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-ack-collision-001",
        broker="live-sim",
        now=clock,
    )

    order = _order("live-ack-collision-001")
    gateway.submit_order(order)
    gateway.submit_order(order)

    ack_events = sink.list_broker_events(
        "run-ack-collision-001",
        event_type="order_ack",
        order_id="live-ack-collision-001",
    )
    assert {event.event_id for event in ack_events} == {
        "run-ack-collision-001:live-sim:order_ack:live-ack-collision-001:submitted",
        "run-ack-collision-001:live-sim:order_ack:"
        "live-ack-collision-001:submitted:attempt-2",
    }
    assert [event.event_time for event in ack_events] == [
        "2026-06-01T09:30:00+00:00",
        "2026-06-01T09:31:00+00:00",
    ]


def test_reconnected_wrapper_recovers_broker_order_id_from_recorded_ack() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-replay-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-001"))

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-replay-001",
        broker="live-sim",
        now=clock,
    )
    reconnected_session.query_fills("live-reconnect-001")
    reconnected_session.cancel_order("live-reconnect-001")

    events = sink.list_broker_events("run-reconnect-replay-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["fill"].broker_order_id == "broker-live-reconnect-001"
    assert by_type["fill"].payload["broker_order_id"] == ("broker-live-reconnect-001")
    assert by_type["cancel"].broker_order_id == "broker-live-reconnect-001"
    assert by_type["cancel"].payload["broker_order_id"] == ("broker-live-reconnect-001")


def test_reconnected_wrapper_falls_back_to_recorded_ack_when_lookup_misses() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-lookup-miss-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-lookup-miss-001"))

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-lookup-miss-001",
        broker="live-sim",
        now=clock,
        broker_order_id_lookup=lambda _order_id: None,
    )
    reconnected_session.query_fills("live-reconnect-lookup-miss-001")
    reconnected_session.cancel_order("live-reconnect-lookup-miss-001")

    events = sink.list_broker_events("run-reconnect-lookup-miss-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["fill"].broker_order_id == ("broker-live-reconnect-lookup-miss-001")
    assert by_type["fill"].payload["broker_order_id"] == (
        "broker-live-reconnect-lookup-miss-001"
    )
    assert by_type["cancel"].broker_order_id == (
        "broker-live-reconnect-lookup-miss-001"
    )
    assert by_type["cancel"].payload["broker_order_id"] == (
        "broker-live-reconnect-lookup-miss-001"
    )


def test_reconnected_wrapper_treats_blank_lookup_value_as_miss() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-blank-lookup-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-blank-lookup-001"))

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-blank-lookup-001",
        broker="live-sim",
        now=clock,
        broker_order_id_lookup=lambda _order_id: "   ",
    )
    reconnected_session.query_fills("live-reconnect-blank-lookup-001")
    reconnected_session.cancel_order("live-reconnect-blank-lookup-001")

    events = sink.list_broker_events("run-reconnect-blank-lookup-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["fill"].broker_order_id == ("broker-live-reconnect-blank-lookup-001")
    assert by_type["fill"].payload["broker_order_id"] == (
        "broker-live-reconnect-blank-lookup-001"
    )
    assert by_type["cancel"].broker_order_id == (
        "broker-live-reconnect-blank-lookup-001"
    )
    assert by_type["cancel"].payload["broker_order_id"] == (
        "broker-live-reconnect-blank-lookup-001"
    )


def test_reconnected_wrapper_skips_blank_recorded_broker_order_ids() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-blank-recorded-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-blank-recorded-001"))
    sink.save_broker_event(
        BrokerEventRecord(
            event_id="run-reconnect-blank-recorded-001:live-sim:fill:blank-history",
            run_id="run-reconnect-blank-recorded-001",
            broker="live-sim",
            event_type="fill",
            event_time="2026-06-01T09:30:59+00:00",
            order_id="live-reconnect-blank-recorded-001",
            broker_order_id="   ",
            fill_id="blank-history",
            instrument_id=510300,
            status="partially_filled",
            correlation_id="live-reconnect-blank-recorded-001",
            payload={"broker_order_id": "   "},
            created_at="2026-06-01T09:30:59+00:00",
        )
    )

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-blank-recorded-001",
        broker="live-sim",
        now=clock,
    )
    reconnected_session.query_fills("live-reconnect-blank-recorded-001")
    reconnected_session.cancel_order("live-reconnect-blank-recorded-001")

    events = sink.list_broker_events("run-reconnect-blank-recorded-001")
    by_type = {event.event_type: event for event in events}
    assert by_type["fill"].broker_order_id == (
        "broker-live-reconnect-blank-recorded-001"
    )
    assert by_type["fill"].payload["broker_order_id"] == (
        "broker-live-reconnect-blank-recorded-001"
    )
    assert by_type["cancel"].broker_order_id == (
        "broker-live-reconnect-blank-recorded-001"
    )
    assert by_type["cancel"].payload["broker_order_id"] == (
        "broker-live-reconnect-blank-recorded-001"
    )


def test_reconnected_wrapper_recovers_broker_order_id_only_from_recorded_ack() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-ack-authority-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-001"))
    sink.save_broker_event(
        BrokerEventRecord(
            event_id=(
                "run-reconnect-ack-authority-001:live-sim:fill:dirty-non-ack-link"
            ),
            run_id="run-reconnect-ack-authority-001",
            broker="live-sim",
            event_type="fill",
            event_time="2026-06-01T09:30:59+00:00",
            order_id="live-reconnect-001",
            broker_order_id="broker-dirty-non-ack",
            fill_id="dirty-non-ack-link",
            instrument_id=510300,
            status="partially_filled",
            correlation_id="live-reconnect-001",
            payload={"broker_order_id": "broker-dirty-non-ack"},
            created_at="2026-06-01T09:30:59+00:00",
        )
    )

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-ack-authority-001",
        broker="live-sim",
        now=clock,
    )
    reconnected_session.query_fills("live-reconnect-001")
    reconnected_session.cancel_order("live-reconnect-001")

    events = sink.list_broker_events("run-reconnect-ack-authority-001")
    replayed_fill = next(
        event for event in events if event.fill_id == "broker-fill-001"
    )
    cancel = next(event for event in events if event.event_type == "cancel")
    assert replayed_fill.broker_order_id == "broker-live-reconnect-001"
    assert replayed_fill.payload["broker_order_id"] == "broker-live-reconnect-001"
    assert cancel.broker_order_id == "broker-live-reconnect-001"
    assert cancel.payload["broker_order_id"] == "broker-live-reconnect-001"


def test_reconnected_wrapper_recovers_broker_order_id_only_from_same_broker_ack() -> (
    None
):
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 32, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-broker-scope-001",
        broker="live-sim",
        now=clock,
    )

    first_session.submit_order(_order("live-reconnect-broker-scope-001"))
    sink.save_broker_event(
        BrokerEventRecord(
            event_id=(
                "run-reconnect-broker-scope-001:other-sim:order_ack:"
                "live-reconnect-broker-scope-001:submitted"
            ),
            run_id="run-reconnect-broker-scope-001",
            broker="other-sim",
            event_type="order_ack",
            event_time="2026-06-01T09:30:59+00:00",
            order_id="live-reconnect-broker-scope-001",
            broker_order_id="other-broker-live-reconnect-broker-scope-001",
            instrument_id=510300,
            status="submitted",
            correlation_id="live-reconnect-broker-scope-001",
            payload={"broker_order_id": "other-broker-live-reconnect-broker-scope-001"},
            created_at="2026-06-01T09:30:59+00:00",
        )
    )

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-broker-scope-001",
        broker="live-sim",
        now=clock,
    )
    reconnected_session.query_fills("live-reconnect-broker-scope-001")
    reconnected_session.cancel_order("live-reconnect-broker-scope-001")

    events = sink.list_broker_events("run-reconnect-broker-scope-001")
    replayed_fill = next(
        event for event in events if event.fill_id == "broker-fill-001"
    )
    cancel = next(
        event
        for event in events
        if event.event_type == "cancel"
        and event.order_id == "live-reconnect-broker-scope-001"
    )
    assert replayed_fill.broker_order_id == "broker-live-reconnect-broker-scope-001"
    assert replayed_fill.payload["broker_order_id"] == (
        "broker-live-reconnect-broker-scope-001"
    )
    assert cancel.broker_order_id == "broker-live-reconnect-broker-scope-001"
    assert cancel.payload["broker_order_id"] == (
        "broker-live-reconnect-broker-scope-001"
    )


def test_fill_event_ids_are_order_scoped_to_avoid_cross_order_collisions() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=OrderScopedFillIdBrokerGateway(),
        event_sink=sink,
        run_id="run-live-002",
        broker="live-sim",
        now=_fixed_now,
    )

    gateway.submit_order(_order("live-001"))
    gateway.submit_order(_order("live-002"))

    fill_events = sink.list_broker_events("run-live-002", event_type="fill")
    assert {event.order_id for event in fill_events} == {"live-001", "live-002"}
    assert {event.event_id for event in fill_events} == {
        "run-live-002:live-sim:fill:live-001:broker-fill-001:100:0",
        "run-live-002:live-sim:fill:live-002:broker-fill-001:100:0",
    }


def test_same_fill_id_progress_updates_are_recorded_as_distinct_events() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ProgressiveFillReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-fill-progress-001",
        broker="live-sim",
        now=_fixed_now,
    )

    gateway.submit_order(_order("live-fill-progress-001"))
    gateway.query_fills("live-fill-progress-001")
    gateway.query_fills("live-fill-progress-001")

    fill_events = sink.list_broker_events(
        "run-fill-progress-001",
        event_type="fill",
    )
    assert [event.payload["cumulative_quantity"] for event in fill_events] == [40, 100]
    assert [event.payload["leaves_quantity"] for event in fill_events] == [60, 0]
    assert [event.status for event in fill_events] == [
        "partially_filled",
        "filled",
    ]
    assert {event.event_id for event in fill_events} == {
        "run-fill-progress-001:live-sim:fill:live-fill-progress-001:"
        "broker-fill-progress-001:40:60",
        "run-fill-progress-001:live-sim:fill:live-fill-progress-001:"
        "broker-fill-progress-001:100:0",
    }


def test_same_fill_progress_with_revised_economics_records_fill_revision() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=CorrectedFillReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-fill-revision-001",
        broker="live-sim",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 3, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 4, tzinfo=UTC),
        ),
    )

    gateway.submit_order(_order("live-fill-revision-001"))
    gateway.query_fills("live-fill-revision-001")
    gateway.query_fills("live-fill-revision-001")

    fill_events = sink.list_broker_events(
        "run-fill-revision-001",
        event_type="fill",
    )
    assert [event.event_id for event in fill_events] == [
        "run-fill-revision-001:live-sim:fill:live-fill-revision-001:"
        "broker-fill-corrected-001:100:0",
        "run-fill-revision-001:live-sim:fill:live-fill-revision-001:"
        "broker-fill-corrected-001:100:0:revision-2",
    ]
    assert [event.payload["fill_price"] for event in fill_events] == [10.0, 10.05]
    assert [event.payload["fee"] for event in fill_events] == [1.0, 1.1]
    assert [event.event_time for event in fill_events] == [
        "2026-06-01T09:31:00+00:00",
        "2026-06-01T09:32:00+00:00",
    ]


def test_same_fill_progress_with_revised_broker_order_link_records_fill_revision() -> (
    None
):
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=CorrectedBrokerOrderLinkReplayGateway(),
        event_sink=sink,
        run_id="run-fill-link-revision-001",
        broker="live-sim",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 2, tzinfo=UTC),
        ),
    )

    order = _order("live-fill-link-revision-001")
    gateway.submit_order(order)
    gateway.submit_order(order)

    ack_events = sink.list_broker_events(
        "run-fill-link-revision-001",
        event_type="order_ack",
    )
    assert [event.broker_order_id for event in ack_events] == [
        "broker-old-live-fill-link-revision-001",
        "broker-new-live-fill-link-revision-001",
    ]
    fill_events = sink.list_broker_events(
        "run-fill-link-revision-001",
        event_type="fill",
    )
    assert [event.event_id for event in fill_events] == [
        "run-fill-link-revision-001:live-sim:fill:live-fill-link-revision-001:"
        "broker-fill-link-001:100:0",
        "run-fill-link-revision-001:live-sim:fill:live-fill-link-revision-001:"
        "broker-fill-link-001:100:0:revision-2",
    ]
    assert [event.broker_order_id for event in fill_events] == [
        "broker-old-live-fill-link-revision-001",
        "broker-new-live-fill-link-revision-001",
    ]
    assert [event.payload["broker_order_id"] for event in fill_events] == [
        "broker-old-live-fill-link-revision-001",
        "broker-new-live-fill-link-revision-001",
    ]
    assert [event.payload["fill_price"] for event in fill_events] == [10.0, 10.0]


def test_submit_records_ack_when_immediate_fill_query_fails() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=FillQueryFailingBrokerGateway(),
        event_sink=sink,
        run_id="run-live-003",
        broker="live-sim",
        now=_fixed_now,
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    ticket = gateway.submit_order(_order("live-003"))

    assert ticket.status is OrderStatus.SUBMITTED
    events = sink.list_broker_events("run-live-003")
    assert [(event.event_type, event.order_id, event.status) for event in events] == [
        ("fill_query_error", "live-003", "failed"),
        ("order_ack", "live-003", "submitted"),
    ]
    error = next(event for event in events if event.event_type == "fill_query_error")
    assert error.event_id == (
        "run-live-003:live-sim:fill_query_error:live-003:failed:"
        "2026-06-01T09:30:00+00:00"
    )
    assert error.broker_order_id == "broker-live-003"
    assert error.payload["broker_order_id"] == "broker-live-003"
    assert error.payload["error_type"] == "RuntimeError"
    assert error.payload["message"] == "fill query unavailable for live-003"


def test_direct_fill_query_errors_are_recorded_as_distinct_attempts() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=FillQueryFailingBrokerGateway(),
        event_sink=sink,
        run_id="run-live-query-error-001",
        broker="live-sim",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 35, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 35, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 36, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 36, 1, tzinfo=UTC),
        ),
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    with pytest.raises(RuntimeError, match="fill query unavailable"):
        gateway.query_fills("live-query-error-001")
    with pytest.raises(RuntimeError, match="fill query unavailable"):
        gateway.query_fills("live-query-error-001")

    events = sink.list_broker_events(
        "run-live-query-error-001",
        event_type="fill_query_error",
    )
    assert [event.event_id for event in events] == [
        "run-live-query-error-001:live-sim:fill_query_error:"
        "live-query-error-001:failed:2026-06-01T09:35:00+00:00",
        "run-live-query-error-001:live-sim:fill_query_error:"
        "live-query-error-001:failed:2026-06-01T09:36:00+00:00",
    ]
    assert [(event.order_id, event.status) for event in events] == [
        ("live-query-error-001", "failed"),
        ("live-query-error-001", "failed"),
    ]
    assert [event.broker_order_id for event in events] == [
        "broker-live-query-error-001",
        "broker-live-query-error-001",
    ]


def test_cancel_errors_are_recorded_as_distinct_failed_attempts() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ResponseFailingBrokerGateway(),
        event_sink=sink,
        run_id="run-cancel-error-001",
        broker="live-sim",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 37, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 37, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 38, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 38, 1, tzinfo=UTC),
        ),
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    with pytest.raises(RuntimeError, match="cancel transport unavailable"):
        gateway.cancel_order("live-cancel-error-001")
    with pytest.raises(RuntimeError, match="cancel transport unavailable"):
        gateway.cancel_order("live-cancel-error-001")

    events = sink.list_broker_events(
        "run-cancel-error-001",
        event_type="cancel",
    )
    assert [event.event_id for event in events] == [
        "run-cancel-error-001:live-sim:cancel:live-cancel-error-001:failed:"
        "2026-06-01T09:37:00+00:00",
        "run-cancel-error-001:live-sim:cancel:live-cancel-error-001:failed:"
        "2026-06-01T09:38:00+00:00",
    ]
    assert [event.status for event in events] == ["failed", "failed"]
    assert [event.broker_order_id for event in events] == [
        "broker-live-cancel-error-001",
        "broker-live-cancel-error-001",
    ]
    assert [event.payload["error_type"] for event in events] == [
        "RuntimeError",
        "RuntimeError",
    ]
    assert [event.payload["message"] for event in events] == [
        "cancel transport unavailable for live-cancel-error-001",
        "cancel transport unavailable for live-cancel-error-001",
    ]


def test_reject_errors_are_recorded_as_distinct_failed_attempts() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ResponseFailingBrokerGateway(),
        event_sink=sink,
        run_id="run-reject-error-001",
        broker="live-sim",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 39, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 39, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 40, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 40, 1, tzinfo=UTC),
        ),
        broker_order_id_lookup=lambda order_id: f"broker-{order_id}",
    )

    with pytest.raises(RuntimeError, match="reject transport unavailable"):
        gateway.reject_order("live-reject-error-001", "risk limit")
    with pytest.raises(RuntimeError, match="reject transport unavailable"):
        gateway.reject_order("live-reject-error-001", "risk limit")

    events = sink.list_broker_events(
        "run-reject-error-001",
        event_type="reject",
    )
    assert [event.event_id for event in events] == [
        "run-reject-error-001:live-sim:reject:live-reject-error-001:failed:"
        "2026-06-01T09:39:00+00:00",
        "run-reject-error-001:live-sim:reject:live-reject-error-001:failed:"
        "2026-06-01T09:40:00+00:00",
    ]
    assert [event.status for event in events] == ["failed", "failed"]
    assert [event.broker_order_id for event in events] == [
        "broker-live-reject-error-001",
        "broker-live-reject-error-001",
    ]
    assert [event.payload["reason"] for event in events] == [
        "risk limit",
        "risk limit",
    ]
    assert [event.payload["error_type"] for event in events] == [
        "RuntimeError",
        "RuntimeError",
    ]
    assert [event.payload["message"] for event in events] == [
        "reject transport unavailable for live-reject-error-001",
        "reject transport unavailable for live-reject-error-001",
    ]
