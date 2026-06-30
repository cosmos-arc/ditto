"""BrokerGateway broker-event recording conformance tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import cast

import orjson
import pytest
from ditto_execution.audit import ExecutionAuditService, ExecutionRepairAuditSink
from ditto_execution.broker.contracts import (
    REQUIRED_BROKER_GATEWAY_CAPABILITIES,
    BrokerGatewayDescriptor,
    validate_broker_gateway_descriptor,
)
from ditto_execution.broker.recording import BrokerEventRecordingGateway
from ditto_execution.models import (
    STANDARD_BROKER_EVENT_TYPES,
    BrokerEventRecord,
    FillRecord,
)
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.reconciliation import (
    AmendLocalFillRepairHandler,
    BrokerOrderLinkIndex,
    ImportBrokerFillRepairHandler,
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
    plan_repair,
    reconcile,
)
from ditto_execution.reconciliation.executor import (
    BrokerRefreshRepairHandler,
    RepairActionExecutor,
    ReviewOrderStatusRepairHandler,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import Account, AccountView


class InMemoryBrokerEventSink:
    """Small in-memory stand-in for BrokerEventDataPort."""

    def __init__(self) -> None:
        self._records: dict[str, BrokerEventRecord] = {}
        self._sequence: dict[str, int] = {}
        self._next_sequence = 0

    def save_broker_event(self, record: BrokerEventRecord) -> None:
        existing = self._records.get(record.event_id)
        if existing is None:
            self._sequence[record.event_id] = self._next_sequence
            self._next_sequence += 1
            self._records[record.event_id] = record
            return
        self._records[record.event_id] = replace(
            existing,
            order_id=self._backfill_text(existing.order_id, record.order_id),
            broker_order_id=self._backfill_text(
                existing.broker_order_id,
                record.broker_order_id,
            ),
            fill_id=self._backfill_text(existing.fill_id, record.fill_id),
            instrument_id=existing.instrument_id or record.instrument_id,
            correlation_id=self._backfill_text(
                existing.correlation_id,
                record.correlation_id,
            ),
        )

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
        del start_date, end_date
        records = [
            record for record in self._records.values() if record.run_id == run_id
        ]
        if event_type is not None:
            records = [record for record in records if record.event_type == event_type]
        if order_id is not None:
            records = [record for record in records if record.order_id == order_id]
        if broker_order_id is not None:
            records = [
                record
                for record in records
                if record.broker_order_id == broker_order_id
                or record.payload.get("broker_order_id") == broker_order_id
            ]
        if fill_id is not None:
            records = [record for record in records if record.fill_id == fill_id]
        return sorted(
            records,
            key=lambda record: (
                record.event_time,
                self._sequence[record.event_id],
            ),
        )

    @staticmethod
    def _backfill_text(current: str | None, candidate: str | None) -> str | None:
        if current is not None and current.strip():
            return current
        if candidate is None or not candidate.strip():
            return current
        return candidate


def test_in_memory_broker_event_sink_preserves_first_duplicate_callback() -> None:
    sink = InMemoryBrokerEventSink()
    sink.save_broker_event(
        BrokerEventRecord(
            event_id="BE-DUP",
            run_id="RUN-001",
            broker="live-sim",
            event_type="fill",
            event_time="2026-06-01T09:31:00+00:00",
            order_id="ORD-001",
            broker_order_id=None,
            fill_id="FILL-001",
            instrument_id=510300,
            status="partially_filled",
            correlation_id="ORD-001",
            payload={"seq": 1, "venue_status": "PartiallyFilled"},
            created_at="2026-06-01T10:00:00+00:00",
        )
    )
    sink.save_broker_event(
        BrokerEventRecord(
            event_id="BE-DUP",
            run_id="RUN-001",
            broker="live-sim",
            event_type="fill",
            event_time="2026-06-01T09:40:00+00:00",
            order_id="ORD-001",
            broker_order_id="BRK-001",
            fill_id="FILL-001",
            instrument_id=510300,
            status="filled",
            correlation_id="ORD-001",
            payload={"seq": 2, "venue_status": "Filled"},
            created_at="2026-06-01T10:05:00+00:00",
        )
    )

    events = sink.list_broker_events("RUN-001")

    assert len(events) == 1
    assert events[0].broker_order_id == "BRK-001"
    assert events[0].event_time == "2026-06-01T09:31:00+00:00"
    assert events[0].status == "partially_filled"
    assert events[0].payload == {"seq": 1, "venue_status": "PartiallyFilled"}
    assert events[0].created_at == "2026-06-01T10:00:00+00:00"


class ManualBrokerGateway:
    """Controllable gateway used to verify non-fill event recording."""

    def __init__(self) -> None:
        self.connected = False

    def describe(self) -> BrokerGatewayDescriptor:
        return BrokerGatewayDescriptor(
            gateway_id="manual",
            mode="paper",
            capabilities=REQUIRED_BROKER_GATEWAY_CAPABILITIES,
            supported_event_types=STANDARD_BROKER_EVENT_TYPES,
        )

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


class UniqueFillIdBrokerGateway(ManualBrokerGateway):
    """Gateway fixture that returns order-unique broker fill IDs."""

    def __init__(self, fill_quantity: int = 40) -> None:
        super().__init__()
        self._fill_quantity = fill_quantity
        self._orders: dict[str, Order] = {}

    def submit_order(self, order: Order) -> OrderTicket:
        self._orders[order.order_id] = order
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        order = self._orders[order_id]
        filled_quantity = min(self._fill_quantity, order.quantity)
        leaves_quantity = order.quantity - filled_quantity
        status_time = datetime(2026, 6, 1, 9, 31, tzinfo=UTC)
        return (
            FillEvent(
                fill_id=f"broker-fill-{order_id}",
                order_id=order_id,
                instrument_id=InstrumentId(510300),
                direction=OrderSide.BUY,
                filled_quantity=filled_quantity,
                fill_price=10.0,
                fee=0.0,
                slippage=0.0,
                event_time=status_time,
                cumulative_quantity=filled_quantity,
                leaves_quantity=leaves_quantity,
            ),
        )


class SingleSharedFillIdBrokerGateway(ManualBrokerGateway):
    """Gateway fixture whose broker fill ID is reused across different orders."""

    def submit_order(self, order: Order) -> OrderTicket:
        return OrderTicket(
            order=order,
            status=OrderStatus.SUBMITTED,
            broker_order_id=f"broker-{order.order_id}",
        )

    def cancel_order(self, order_id: str) -> bool:
        del order_id
        return True

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


@dataclass(frozen=True)
class _AllMismatchCallbackScenario:
    qty_order: Order
    price_order: Order
    status_order: Order
    missing_order: Order
    extra_order: Order
    missing_gateway: BrokerEventRecordingGateway
    fill_events: list[BrokerEventRecord]
    broker_order_ids_by_order: dict[str, str]
    broker_order_ids_by_order_fill: dict[tuple[str, str], str]


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


def _submit_all_mismatch_callback_scenario(
    *,
    run_id: str,
    sink: InMemoryBrokerEventSink,
) -> _AllMismatchCallbackScenario:
    clock = SequenceClock(
        *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(20))
    )
    qty_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=clock,
    )
    price_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="beta",
        now=clock,
    )
    status_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="gamma",
        now=clock,
    )
    missing_gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id=run_id,
        broker="delta",
        now=clock,
    )
    extra_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="epsilon",
        now=clock,
    )
    qty_order = _order("callback-all-sequence-qty-001", quantity=100, price=10.0)
    price_order = _order("callback-all-sequence-price-001", quantity=40, price=10.25)
    status_order = _order("callback-all-sequence-status-001", quantity=40, price=10.0)
    missing_order = _order("callback-all-sequence-missing-001", quantity=100)
    extra_order = _order("callback-all-sequence-extra-001", quantity=40)

    qty_gateway.submit_order(qty_order)
    price_gateway.submit_order(price_order)
    status_gateway.submit_order(status_order)
    missing_gateway.submit_order(missing_order)
    extra_gateway.submit_order(extra_order)

    ack_events = sink.list_broker_events(run_id, event_type="order_ack")
    fill_events = sink.list_broker_events(run_id, event_type="fill")
    broker_order_ids_by_order = {
        cast(str, event.order_id): cast(str, event.broker_order_id)
        for event in ack_events
        if event.order_id is not None and event.broker_order_id is not None
    }
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    return _AllMismatchCallbackScenario(
        qty_order=qty_order,
        price_order=price_order,
        status_order=status_order,
        missing_order=missing_order,
        extra_order=extra_order,
        missing_gateway=missing_gateway,
        fill_events=fill_events,
        broker_order_ids_by_order=broker_order_ids_by_order,
        broker_order_ids_by_order_fill=broker_order_ids_by_order_fill,
    )


def _all_mismatch_report(
    *,
    report_id: str,
    scenario: _AllMismatchCallbackScenario,
) -> ReconciliationReport:
    return reconcile(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=scenario.qty_order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
            OrderTicket(
                order=scenario.price_order,
                status=OrderStatus.FILLED,
                filled_quantity=40,
                filled_price=10.25,
                average_fill_price=10.25,
            ),
            OrderTicket(
                order=scenario.status_order,
                status=OrderStatus.SUBMITTED,
                filled_quantity=40,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
            OrderTicket(
                order=scenario.missing_order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
        ],
        actual=[_fill_from_broker_event(event) for event in scenario.fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order=scenario.broker_order_ids_by_order,
            by_order_fill=scenario.broker_order_ids_by_order_fill,
        ),
    )


def _current_all_mismatch_fill_records() -> tuple[FillRecord, FillRecord]:
    return (
        FillRecord(
            fill_id="broker-fill-callback-all-sequence-qty-001",
            intent_id="callback-all-sequence-qty-001",
            strategy_id="strategy-live-sim",
            trade_date="2026-06-01",
            instrument_id=510300,
            direction="buy",
            quantity=40,
            fill_price=10.0,
            fee=0.0,
            slippage=0.0,
            notes="imported partial broker fill before repair",
            created_at="2026-06-01T09:31:00Z",
        ),
        FillRecord(
            fill_id="broker-fill-callback-all-sequence-price-001",
            intent_id="callback-all-sequence-price-001",
            strategy_id="strategy-live-sim",
            trade_date="2026-06-01",
            instrument_id=510300,
            direction="buy",
            quantity=40,
            fill_price=10.25,
            fee=0.0,
            slippage=0.0,
            notes="imported expected-price fill before repair",
            created_at="2026-06-01T09:31:00Z",
        ),
    )


def _fill_from_broker_event(event: BrokerEventRecord) -> FillEvent:
    return FillEvent(
        fill_id=event.fill_id or "",
        order_id=event.order_id or "",
        instrument_id=InstrumentId(cast(int, event.instrument_id)),
        direction=OrderSide(cast(str, event.payload["direction"])),
        filled_quantity=cast(int, event.payload["filled_quantity"]),
        fill_price=cast(float, event.payload["fill_price"]),
        fee=cast(float, event.payload["fee"]),
        slippage=cast(float, event.payload["slippage"]),
        event_time=datetime.fromisoformat(event.event_time),
        cumulative_quantity=cast(int, event.payload["cumulative_quantity"]),
        leaves_quantity=cast(int, event.payload["leaves_quantity"]),
    )


class _BrokerEventFillImportSource:
    def __init__(self, events: dict[tuple[str, str], BrokerEventRecord]) -> None:
        self._events = events
        self.requested_action_ids: list[str] = []
        self.requested_fill_ids: list[str] = []

    def get_fill_record(self, action: RepairActionRecord) -> FillRecord | None:
        if action.fill_id is None:
            return None
        self.requested_action_ids.append(action.action_id)
        self.requested_fill_ids.append(action.fill_id)
        event = self._events.get((action.order_id, action.fill_id))
        if event is None:
            return None
        return FillRecord(
            fill_id=action.fill_id,
            intent_id=action.client_order_id or action.order_id,
            strategy_id="strategy-live-sim",
            trade_date=action.trade_date,
            instrument_id=cast(int, event.instrument_id),
            direction=cast(str, event.payload["direction"]),
            quantity=cast(int, event.payload["filled_quantity"]),
            fill_price=cast(float, event.payload["fill_price"]),
            fee=cast(float, event.payload["fee"]),
            slippage=cast(float, event.payload["slippage"]),
            notes="imported from recorded broker event",
            created_at=event.event_time,
        )


def _approve_all_mismatch_manual_actions(
    workflow_store: SQLiteRepairWorkflowStore,
    report_id: str,
) -> None:
    for index, reason in (
        (0, "amend reviewed partial broker fill"),
        (1, "amend reviewed broker fill price"),
        (2, "OMS and broker status reviewed"),
        (4, "import reviewed extra broker fill"),
    ):
        workflow_store.approve_action(
            f"{report_id}:{index:04d}",
            reviewer="ops",
            reason=reason,
            reviewed_at="2026-06-01T09:33:00Z",
        )


def _all_mismatch_fill_import_source(
    scenario: _AllMismatchCallbackScenario,
) -> _BrokerEventFillImportSource:
    return _BrokerEventFillImportSource(
        {
            (cast(str, event.order_id), cast(str, event.fill_id)): event
            for event in scenario.fill_events
            if event.order_id is not None and event.fill_id is not None
        }
    )


class _BrokerEventFillAmendmentSource:
    def __init__(self, amended_fills: dict[str, FillRecord]) -> None:
        self._amended_fills = amended_fills
        self.requested_action_ids: list[str] = []
        self.requested_fill_ids: list[str] = []

    def get_amended_fill_record(
        self,
        action: RepairActionRecord,
        current: FillRecord,
    ) -> FillRecord | None:
        del current
        if action.fill_id is None:
            return None
        self.requested_action_ids.append(action.action_id)
        self.requested_fill_ids.append(action.fill_id)
        return self._amended_fills.get(action.fill_id)


class _BrokerEventOrderStatusReviewSource:
    def __init__(self, reviewed_statuses: dict[str, str]) -> None:
        self._reviewed_statuses = reviewed_statuses
        self.requested_action_ids: list[str] = []
        self.observed_current_statuses: list[str] = []

    def get_reviewed_order_status(
        self,
        action: RepairActionRecord,
        current_status: str,
    ) -> str | None:
        self.requested_action_ids.append(action.action_id)
        self.observed_current_statuses.append(current_status)
        return self._reviewed_statuses.get(action.action_id)


class _InMemoryLocalFillStore:
    def __init__(self) -> None:
        self.records: dict[str, FillRecord] = {}

    def get_fill(self, fill_id: str) -> FillRecord | None:
        return self.records.get(fill_id)

    def save_fill(self, record: FillRecord) -> None:
        self.records[record.fill_id] = record

    def replace_fill(self, record: FillRecord) -> bool:
        if record.fill_id not in self.records:
            return False
        self.records[record.fill_id] = record
        return True


class _InMemoryLocalOrderStatusStore:
    def __init__(self, statuses: dict[str, str]) -> None:
        self.statuses = statuses
        self.updated: list[tuple[str, str, tuple[str, ...]]] = []

    def get_order_status(self, order_id: str) -> str | None:
        return self.statuses.get(order_id)

    def update_order_status(
        self,
        order_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        if self.statuses.get(order_id) not in expected_current:
            return False
        self.updated.append((order_id, status, expected_current))
        self.statuses[order_id] = status
        return True


@dataclass(frozen=True)
class _AllMismatchRetryReplayFixture:
    run_id: str
    report_id: str
    scenario: _AllMismatchCallbackScenario
    workflow_store: SQLiteRepairWorkflowStore
    qty_fill_id: str
    price_fill_id: str
    extra_fill_id: str
    current_price_fill: FillRecord
    amended_qty_fill: FillRecord
    amended_price_fill: FillRecord
    local_fills: _InMemoryLocalFillStore
    local_orders: _InMemoryLocalOrderStatusStore
    audit_service: ExecutionAuditService


def _prepare_all_mismatch_retry_replay_fixture(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> _AllMismatchRetryReplayFixture:
    run_id = "run-callback-all-mismatch-retry-replay-001"
    report_id = "rec-callback-all-mismatch-retry-replay-001"
    sink = InMemoryBrokerEventSink()
    scenario = _submit_all_mismatch_callback_scenario(run_id=run_id, sink=sink)
    report = _all_mismatch_report(report_id=report_id, scenario=scenario)
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    _approve_all_mismatch_manual_actions(workflow_store, report_id)
    qty_fill_id = "broker-fill-callback-all-sequence-qty-001"
    price_fill_id = "broker-fill-callback-all-sequence-price-001"
    extra_fill_id = "broker-fill-callback-all-sequence-extra-001"
    current_qty_fill, current_price_fill = _current_all_mismatch_fill_records()
    amended_qty_fill = replace(
        current_qty_fill,
        quantity=100,
        notes="amended from callback-derived retry sequence",
        created_at="2026-06-01T09:35:00Z",
    )
    amended_price_fill = replace(
        current_price_fill,
        fill_price=10.0,
        notes="amended from callback-derived retry replay",
        created_at="2026-06-01T09:36:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_qty_fill)
    local_fills.save_fill(current_price_fill)
    local_orders = _InMemoryLocalOrderStatusStore(
        {"callback-all-sequence-status-001": "submitted"}
    )
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    return _AllMismatchRetryReplayFixture(
        run_id=run_id,
        report_id=report_id,
        scenario=scenario,
        workflow_store=workflow_store,
        qty_fill_id=qty_fill_id,
        price_fill_id=price_fill_id,
        extra_fill_id=extra_fill_id,
        current_price_fill=current_price_fill,
        amended_qty_fill=amended_qty_fill,
        amended_price_fill=amended_price_fill,
        local_fills=local_fills,
        local_orders=local_orders,
        audit_service=audit_service,
    )


def _all_mismatch_repair_executor(
    *,
    workflow_store: SQLiteRepairWorkflowStore,
    amendment_source: _BrokerEventFillAmendmentSource,
    review_source: _BrokerEventOrderStatusReviewSource,
    local_fills: _InMemoryLocalFillStore,
    local_orders: _InMemoryLocalOrderStatusStore,
    scenario: _AllMismatchCallbackScenario,
    audit_service: ExecutionAuditService,
    run_id: str,
) -> RepairActionExecutor:
    return RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
            RepairActionType.REFRESH_BROKER_ORDER: BrokerRefreshRepairHandler(
                scenario.missing_gateway
            ),
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_all_mismatch_fill_import_source(scenario),
                local_fill_store=local_fills,
            ),
            RepairActionType.REVIEW_ORDER_STATUS: ReviewOrderStatusRepairHandler(
                review_source=review_source,
                local_order_store=local_orders,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker",
    )


def test_recording_gateway_descriptor_adds_recording_capabilities() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=ManualBrokerGateway(),
        event_sink=sink,
        run_id="run-descriptor-001",
        broker="manual",
        now=_fixed_now,
    )

    descriptor = gateway.describe()

    assert validate_broker_gateway_descriptor(descriptor) is descriptor
    assert descriptor.gateway_id == "recording:manual"
    assert descriptor.mode == "recording"
    assert "event_recording" in descriptor.capabilities
    assert "broker_order_id_recovery" in descriptor.capabilities
    assert descriptor.supported_event_types == STANDARD_BROKER_EVENT_TYPES


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
        ("connect", None, "connected"),
        ("cancel", "cancel-ok", "accepted"),
        ("cancel", "cancel-missing", "rejected"),
        ("reject", "reject-ok", "rejected"),
    ]
    assert events[1].payload["accepted"] is True
    assert events[2].payload["accepted"] is False
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


def test_broker_order_id_query_filters_across_brokers() -> None:
    sink = InMemoryBrokerEventSink()
    alpha = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-broker-order-filter-001",
        broker="alpha",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 3, tzinfo=UTC),
        ),
    )
    beta = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-broker-order-filter-001",
        broker="beta",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 3, tzinfo=UTC),
        ),
    )

    alpha.submit_order(_order("multi-alpha-001"))
    beta.submit_order(_order("multi-beta-001"))

    events = sink.list_broker_events(
        "run-broker-order-filter-001",
        broker_order_id="broker-multi-alpha-001",
    )

    assert [(event.broker, event.event_type, event.order_id) for event in events] == [
        ("alpha", "order_ack", "multi-alpha-001"),
        ("alpha", "fill", "multi-alpha-001"),
    ]


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


def test_reconnected_long_callback_sequence_preserves_recovered_links() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        datetime(2026, 6, 1, 9, 29, 50, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 29, 51, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, 2, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, 3, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, 4, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 5, 5, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 6, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 7, tzinfo=UTC),
        datetime(2026, 6, 1, 10, 7, 1, tzinfo=UTC),
    )
    first_session = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-reconnect-long-sequence-001",
        broker="live-sim",
        now=clock,
    )

    first_session.connect()
    first_session.submit_order(_order("live-reconnect-001"))

    reconnected_session = BrokerEventRecordingGateway(
        gateway=ReconnectedReplayBrokerGateway(),
        event_sink=sink,
        run_id="run-reconnect-long-sequence-001",
        broker="live-sim",
        now=clock,
    )
    reconnected_session.connect()
    reconnected_session.query_fills("live-reconnect-001")
    reconnected_session.query_fills("live-reconnect-001")
    reconnected_session.cancel_order("live-reconnect-001")
    reconnected_session.get_account()

    events = sink.list_broker_events("run-reconnect-long-sequence-001")
    assert [(event.event_type, event.order_id, event.status) for event in events] == [
        ("connect", None, "connected"),
        ("order_ack", "live-reconnect-001", "submitted"),
        ("fill", "live-reconnect-001", "partially_filled"),
        ("connect", None, "connected"),
        ("cancel", "live-reconnect-001", "accepted"),
        ("account_update", None, "snapshot"),
    ]

    order_linked_events = [
        event for event in events if event.event_type in {"order_ack", "fill", "cancel"}
    ]
    assert [event.broker_order_id for event in order_linked_events] == [
        "broker-live-reconnect-001",
        "broker-live-reconnect-001",
        "broker-live-reconnect-001",
    ]
    assert [event.payload["broker_order_id"] for event in order_linked_events] == [
        "broker-live-reconnect-001",
        "broker-live-reconnect-001",
        "broker-live-reconnect-001",
    ]

    fill_events = [event for event in events if event.event_type == "fill"]
    assert [event.event_id for event in fill_events] == [
        "run-reconnect-long-sequence-001:live-sim:fill:"
        "live-reconnect-001:broker-fill-001:40:60"
    ]
    assert fill_events[0].created_at == "2026-06-01T10:05:02+00:00"

    connect_events = [event for event in events if event.event_type == "connect"]
    assert [event.event_id for event in connect_events] == [
        "run-reconnect-long-sequence-001:live-sim:connect:2026-06-01T09:29:50+00:00",
        "run-reconnect-long-sequence-001:live-sim:connect:2026-06-01T10:05:00+00:00",
    ]


def test_recorded_fill_link_survives_reconciliation_repair_plan() -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-repair-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-repair-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    broker_fill_events = sink.list_broker_events(
        "run-callback-repair-001",
        event_type="fill",
    )
    broker_order_ids_by_order = {
        cast(str, event.order_id): cast(str, event.broker_order_id)
        for event in broker_fill_events
        if event.order_id is not None and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-repair-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in broker_fill_events],
        broker_order_links=BrokerOrderLinkIndex(by_order=broker_order_ids_by_order),
    )
    plan = plan_repair(report)

    qty_action = next(
        action
        for action in plan.actions
        if action.mismatch_type is MismatchType.QTY_MISMATCH
    )
    assert qty_action.order_id == "callback-repair-001"
    assert qty_action.broker_order_id == "broker-callback-repair-001"


def test_recorded_ack_link_survives_missing_fill_repair_execution_audit(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id="run-callback-refresh-audit-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-refresh-audit-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    ack_events = sink.list_broker_events(
        "run-callback-refresh-audit-001",
        event_type="order_ack",
    )
    broker_order_ids_by_order = {
        cast(str, event.order_id): cast(str, event.broker_order_id)
        for event in ack_events
        if event.order_id is not None and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-refresh-audit-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            )
        ],
        actual=[],
        broker_order_links=BrokerOrderLinkIndex(by_order=broker_order_ids_by_order),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={"refresh_broker_order": BrokerRefreshRepairHandler(gateway)},
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-callback-refresh-audit-001",
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        "rec-callback-refresh-audit-001",
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(
        "run-callback-refresh-audit-001",
        record_type="repair_execution",
    )
    assert len(rows) == 1
    payload = orjson.loads(rows[0]["payload"])
    assert [result.status for result in results] == ["executed"]
    assert payload["action_type"] == "refresh_broker_order"
    assert payload["client_order_id"] == "callback-refresh-audit-001"
    assert payload["broker_order_id"] == "broker-callback-refresh-audit-001"


def test_recorded_extra_fill_import_execution_audit_preserves_client_order_link(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-extra-import-audit-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-extra-import-audit-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(
        "run-callback-extra-import-audit-001",
        event_type="fill",
    )
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-extra-import-audit-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    workflow_store.approve_action(
        "rec-callback-extra-import-audit-001:0000",
        reviewer="ops",
        reason="import reviewed broker fill",
        reviewed_at="2026-06-01T09:33:00Z",
    )
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    local_fills = _InMemoryLocalFillStore()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            "import_broker_fill": ImportBrokerFillRepairHandler(
                broker_fill_source=_BrokerEventFillImportSource(
                    {
                        (cast(str, event.order_id), cast(str, event.fill_id)): event
                        for event in fill_events
                        if event.order_id is not None and event.fill_id is not None
                    }
                ),
                local_fill_store=local_fills,
            )
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-callback-extra-import-audit-001",
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        "rec-callback-extra-import-audit-001",
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(
        "run-callback-extra-import-audit-001",
        record_type="repair_execution",
    )
    assert [result.status for result in results] == ["executed"]
    assert local_fills.get_fill("broker-fill-001") is not None
    assert len(rows) == 1
    payload = orjson.loads(rows[0]["payload"])
    assert payload["action_type"] == "import_broker_fill"
    assert payload["fill_id"] == "broker-fill-001"
    assert payload["client_order_id"] == "callback-extra-import-audit-001"
    assert payload["broker_order_id"] == "broker-callback-extra-import-audit-001"


def test_recorded_qty_mismatch_amend_execution_audit_preserves_fill_link(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-qty-amend-audit-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-qty-amend-audit-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(
        "run-callback-qty-amend-audit-001",
        event_type="fill",
    )
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-qty-amend-audit-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    workflow_store.approve_action(
        "rec-callback-qty-amend-audit-001:0000",
        reviewer="ops",
        reason="amend reviewed broker fill",
        reviewed_at="2026-06-01T09:33:00Z",
    )
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    current_fill = FillRecord(
        fill_id="broker-fill-001",
        intent_id="callback-qty-amend-audit-001",
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=40,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        notes="imported from recorded broker event",
        created_at="2026-06-01T09:31:00Z",
    )
    amended_fill = FillRecord(
        fill_id="broker-fill-001",
        intent_id="callback-qty-amend-audit-001",
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=100,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        notes="amended from recorded broker event",
        created_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_fill)
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            "amend_local_fill": AmendLocalFillRepairHandler(
                amendment_source=_BrokerEventFillAmendmentSource(
                    {"broker-fill-001": amended_fill}
                ),
                local_fill_store=local_fills,
            )
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-callback-qty-amend-audit-001",
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        "rec-callback-qty-amend-audit-001",
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(
        "run-callback-qty-amend-audit-001",
        record_type="repair_execution",
    )
    assert [result.status for result in results] == ["executed"]
    assert local_fills.get_fill("broker-fill-001") == amended_fill
    assert len(rows) == 1
    payload = orjson.loads(rows[0]["payload"])
    assert payload["action_type"] == "amend_local_fill"
    assert payload["fill_id"] == "broker-fill-001"
    assert payload["client_order_id"] == "callback-qty-amend-audit-001"
    assert payload["broker_order_id"] == "broker-callback-qty-amend-audit-001"


def test_recorded_price_mismatch_amend_execution_audit_preserves_fill_link(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-price-amend-audit-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-price-amend-audit-001", quantity=40, price=10.25)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(
        "run-callback-price-amend-audit-001",
        event_type="fill",
    )
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-price-amend-audit-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=40,
                filled_price=10.25,
                average_fill_price=10.25,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    workflow_store.approve_action(
        "rec-callback-price-amend-audit-001:0000",
        reviewer="ops",
        reason="amend reviewed broker fill price",
        reviewed_at="2026-06-01T09:33:00Z",
    )
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    current_fill = FillRecord(
        fill_id="broker-fill-001",
        intent_id="callback-price-amend-audit-001",
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=40,
        fill_price=10.25,
        fee=0.0,
        slippage=0.0,
        notes="imported from expected local price",
        created_at="2026-06-01T09:31:00Z",
    )
    amended_fill = FillRecord(
        fill_id="broker-fill-001",
        intent_id="callback-price-amend-audit-001",
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=40,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        notes="amended from recorded broker event price",
        created_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_fill)
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            "amend_local_fill": AmendLocalFillRepairHandler(
                amendment_source=_BrokerEventFillAmendmentSource(
                    {"broker-fill-001": amended_fill}
                ),
                local_fill_store=local_fills,
            )
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-callback-price-amend-audit-001",
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        "rec-callback-price-amend-audit-001",
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(
        "run-callback-price-amend-audit-001",
        record_type="repair_execution",
    )
    assert [action.mismatch_type for action in plan.actions] == [
        MismatchType.PRICE_MISMATCH
    ]
    assert [result.status for result in results] == ["executed"]
    assert local_fills.get_fill("broker-fill-001") == amended_fill
    assert len(rows) == 1
    payload = orjson.loads(rows[0]["payload"])
    assert payload["action_type"] == "amend_local_fill"
    assert payload["fill_id"] == "broker-fill-001"
    assert payload["client_order_id"] == "callback-price-amend-audit-001"
    assert payload["broker_order_id"] == "broker-callback-price-amend-audit-001"


def test_recorded_status_mismatch_review_execution_audit_preserves_order_link(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-status-review-audit-001",
        broker="live-sim",
        now=_fixed_now,
    )
    order = _order("callback-status-review-audit-001", quantity=40, price=10.0)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(
        "run-callback-status-review-audit-001",
        event_type="fill",
    )
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-status-review-audit-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.SUBMITTED,
                filled_quantity=40,
                filled_price=10.0,
                average_fill_price=10.0,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    workflow_store.approve_action(
        "rec-callback-status-review-audit-001:0000",
        reviewer="ops",
        reason="OMS and broker status reviewed",
        reviewed_at="2026-06-01T09:33:00Z",
    )
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    local_orders = _InMemoryLocalOrderStatusStore(
        {"callback-status-review-audit-001": "submitted"}
    )
    review_source = _BrokerEventOrderStatusReviewSource(
        {"rec-callback-status-review-audit-001:0000": "filled"}
    )
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            "review_order_status": ReviewOrderStatusRepairHandler(
                review_source=review_source,
                local_order_store=local_orders,
            )
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id="run-callback-status-review-audit-001",
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        "rec-callback-status-review-audit-001",
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(
        "run-callback-status-review-audit-001",
        record_type="repair_execution",
    )
    assert [action.mismatch_type for action in plan.actions] == [
        MismatchType.STATUS_MISMATCH
    ]
    assert plan.actions[0].broker_order_id == "broker-callback-status-review-audit-001"
    assert review_source.requested_action_ids == [
        "rec-callback-status-review-audit-001:0000"
    ]
    assert review_source.observed_current_statuses == ["submitted"]
    assert local_orders.updated == [
        ("callback-status-review-audit-001", "filled", ("submitted",))
    ]
    assert local_orders.get_order_status("callback-status-review-audit-001") == "filled"
    assert [result.status for result in results] == ["executed"]
    assert len(rows) == 1
    payload = orjson.loads(rows[0]["payload"])
    assert payload["action_type"] == "review_order_status"
    assert payload["client_order_id"] == "callback-status-review-audit-001"
    assert payload["broker_order_id"] == "broker-callback-status-review-audit-001"


def test_callback_derived_mixed_repair_sequence_execution_audit_preserves_links(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-mixed-sequence-audit-001"
    report_id = "rec-callback-mixed-sequence-audit-001"
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(12))
    )
    amend_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=clock,
    )
    missing_gateway = BrokerEventRecordingGateway(
        gateway=BrokerAckNoFillGateway(),
        event_sink=sink,
        run_id=run_id,
        broker="beta",
        now=clock,
    )
    extra_gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="gamma",
        now=clock,
    )
    amend_order = _order("callback-sequence-amend-001", quantity=100, price=10.0)
    missing_order = _order("callback-sequence-missing-001", quantity=100, price=10.0)
    extra_order = _order("callback-sequence-extra-001", quantity=40, price=10.0)

    amend_gateway.submit_order(amend_order)
    missing_gateway.submit_order(missing_order)
    extra_gateway.submit_order(extra_order)

    ack_events = sink.list_broker_events(run_id, event_type="order_ack")
    fill_events = sink.list_broker_events(run_id, event_type="fill")
    broker_order_ids_by_order = {
        cast(str, event.order_id): cast(str, event.broker_order_id)
        for event in ack_events
        if event.order_id is not None and event.broker_order_id is not None
    }
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=amend_order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
            OrderTicket(
                order=missing_order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order=broker_order_ids_by_order,
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    workflow_store.approve_action(
        f"{report_id}:0000",
        reviewer="ops",
        reason="amend reviewed partial broker fill",
        reviewed_at="2026-06-01T09:33:00Z",
    )
    workflow_store.approve_action(
        f"{report_id}:0002",
        reviewer="ops",
        reason="import reviewed extra broker fill",
        reviewed_at="2026-06-01T09:34:00Z",
    )
    amend_fill_id = "broker-fill-callback-sequence-amend-001"
    extra_fill_id = "broker-fill-callback-sequence-extra-001"
    current_amend_fill = FillRecord(
        fill_id=amend_fill_id,
        intent_id="callback-sequence-amend-001",
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=40,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        notes="imported partial broker fill before repair",
        created_at="2026-06-01T09:31:00Z",
    )
    amended_fill = replace(
        current_amend_fill,
        quantity=100,
        notes="amended from callback-derived sequence",
        created_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_amend_fill)
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=_BrokerEventFillAmendmentSource(
                    {amend_fill_id: amended_fill}
                ),
                local_fill_store=local_fills,
            ),
            RepairActionType.REFRESH_BROKER_ORDER: BrokerRefreshRepairHandler(
                missing_gateway
            ),
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_BrokerEventFillImportSource(
                    {
                        (cast(str, event.order_id), cast(str, event.fill_id)): event
                        for event in fill_events
                        if event.order_id is not None and event.fill_id is not None
                    }
                ),
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.order_id,
            action.fill_id,
            action.broker_order_id,
        )
        for action in plan.actions
    ] == [
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            "callback-sequence-amend-001",
            amend_fill_id,
            "broker-callback-sequence-amend-001",
        ),
        (
            MismatchType.MISSING_FILL,
            RepairActionType.REFRESH_BROKER_ORDER,
            "callback-sequence-missing-001",
            None,
            "broker-callback-sequence-missing-001",
        ),
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            "callback-sequence-extra-001",
            extra_fill_id,
            "broker-callback-sequence-extra-001",
        ),
    ]
    assert [result.status for result in results] == [
        "executed",
        "executed",
        "executed",
    ]
    assert [result.action_type for result in results] == [
        RepairActionType.AMEND_LOCAL_FILL,
        RepairActionType.REFRESH_BROKER_ORDER,
        RepairActionType.IMPORT_BROKER_FILL,
    ]
    assert local_fills.get_fill(amend_fill_id) == amended_fill
    imported_extra_fill = local_fills.get_fill(extra_fill_id)
    assert imported_extra_fill is not None
    assert imported_extra_fill.intent_id == "callback-sequence-extra-001"
    assert len(rows) == 3
    assert [
        (
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
        )
        for payload in payloads
    ] == [
        (
            "amend_local_fill",
            "callback-sequence-amend-001",
            "broker-callback-sequence-amend-001",
            amend_fill_id,
        ),
        (
            "refresh_broker_order",
            "callback-sequence-missing-001",
            "broker-callback-sequence-missing-001",
            None,
        ),
        (
            "import_broker_fill",
            "callback-sequence-extra-001",
            "broker-callback-sequence-extra-001",
            extra_fill_id,
        ),
    ]


def test_callback_derived_all_mismatch_repair_sequence_execution_audit_preserves_links(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-all-mismatch-sequence-audit-001"
    report_id = "rec-callback-all-mismatch-sequence-audit-001"
    sink = InMemoryBrokerEventSink()
    scenario = _submit_all_mismatch_callback_scenario(run_id=run_id, sink=sink)
    report = _all_mismatch_report(report_id=report_id, scenario=scenario)
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    _approve_all_mismatch_manual_actions(workflow_store, report_id)
    qty_fill_id = "broker-fill-callback-all-sequence-qty-001"
    price_fill_id = "broker-fill-callback-all-sequence-price-001"
    extra_fill_id = "broker-fill-callback-all-sequence-extra-001"
    current_qty_fill, current_price_fill = _current_all_mismatch_fill_records()
    amended_qty_fill = replace(
        current_qty_fill,
        quantity=100,
        notes="amended from callback-derived all-mismatch sequence",
        created_at="2026-06-01T09:35:00Z",
    )
    amended_price_fill = replace(
        current_price_fill,
        fill_price=10.0,
        notes="amended from callback-derived all-mismatch sequence",
        created_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_qty_fill)
    local_fills.save_fill(current_price_fill)
    local_orders = _InMemoryLocalOrderStatusStore(
        {"callback-all-sequence-status-001": "submitted"}
    )
    review_source = _BrokerEventOrderStatusReviewSource({f"{report_id}:0002": "filled"})
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=_BrokerEventFillAmendmentSource(
                    {
                        qty_fill_id: amended_qty_fill,
                        price_fill_id: amended_price_fill,
                    }
                ),
                local_fill_store=local_fills,
            ),
            RepairActionType.REFRESH_BROKER_ORDER: BrokerRefreshRepairHandler(
                scenario.missing_gateway
            ),
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_all_mismatch_fill_import_source(scenario),
                local_fill_store=local_fills,
            ),
            RepairActionType.REVIEW_ORDER_STATUS: ReviewOrderStatusRepairHandler(
                review_source=review_source,
                local_order_store=local_orders,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.order_id,
            action.fill_id,
            action.broker_order_id,
        )
        for action in plan.actions
    ] == [
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            "callback-all-sequence-qty-001",
            qty_fill_id,
            "broker-callback-all-sequence-qty-001",
        ),
        (
            MismatchType.PRICE_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            "callback-all-sequence-price-001",
            price_fill_id,
            "broker-callback-all-sequence-price-001",
        ),
        (
            MismatchType.STATUS_MISMATCH,
            RepairActionType.REVIEW_ORDER_STATUS,
            "callback-all-sequence-status-001",
            None,
            "broker-callback-all-sequence-status-001",
        ),
        (
            MismatchType.MISSING_FILL,
            RepairActionType.REFRESH_BROKER_ORDER,
            "callback-all-sequence-missing-001",
            None,
            "broker-callback-all-sequence-missing-001",
        ),
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            "callback-all-sequence-extra-001",
            extra_fill_id,
            "broker-callback-all-sequence-extra-001",
        ),
    ]
    assert [result.status for result in results] == [
        "executed",
        "executed",
        "executed",
        "executed",
        "executed",
    ]
    assert [result.action_type for result in results] == [
        RepairActionType.AMEND_LOCAL_FILL,
        RepairActionType.AMEND_LOCAL_FILL,
        RepairActionType.REVIEW_ORDER_STATUS,
        RepairActionType.REFRESH_BROKER_ORDER,
        RepairActionType.IMPORT_BROKER_FILL,
    ]
    assert local_fills.get_fill(qty_fill_id) == amended_qty_fill
    assert local_fills.get_fill(price_fill_id) == amended_price_fill
    imported_extra_fill = local_fills.get_fill(extra_fill_id)
    assert imported_extra_fill is not None
    assert imported_extra_fill.intent_id == "callback-all-sequence-extra-001"
    assert local_orders.updated == [
        ("callback-all-sequence-status-001", "filled", ("submitted",))
    ]
    assert len(rows) == 5
    assert [
        (
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
        )
        for payload in payloads
    ] == [
        (
            "amend_local_fill",
            "callback-all-sequence-qty-001",
            "broker-callback-all-sequence-qty-001",
            qty_fill_id,
        ),
        (
            "amend_local_fill",
            "callback-all-sequence-price-001",
            "broker-callback-all-sequence-price-001",
            price_fill_id,
        ),
        (
            "review_order_status",
            "callback-all-sequence-status-001",
            "broker-callback-all-sequence-status-001",
            None,
        ),
        (
            "refresh_broker_order",
            "callback-all-sequence-missing-001",
            "broker-callback-all-sequence-missing-001",
            None,
        ),
        (
            "import_broker_fill",
            "callback-all-sequence-extra-001",
            "broker-callback-all-sequence-extra-001",
            extra_fill_id,
        ),
    ]


def test_callback_derived_failed_amendment_sequence_keeps_unrelated_repairs_executing(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-all-mismatch-failed-amendment-001"
    report_id = "rec-callback-all-mismatch-failed-amendment-001"
    sink = InMemoryBrokerEventSink()
    scenario = _submit_all_mismatch_callback_scenario(run_id=run_id, sink=sink)
    report = _all_mismatch_report(report_id=report_id, scenario=scenario)
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    _approve_all_mismatch_manual_actions(workflow_store, report_id)
    qty_fill_id = "broker-fill-callback-all-sequence-qty-001"
    price_fill_id = "broker-fill-callback-all-sequence-price-001"
    extra_fill_id = "broker-fill-callback-all-sequence-extra-001"
    current_qty_fill, current_price_fill = _current_all_mismatch_fill_records()
    amended_qty_fill = replace(
        current_qty_fill,
        quantity=100,
        notes="amended from callback-derived retry sequence",
        created_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_qty_fill)
    local_fills.save_fill(current_price_fill)
    local_orders = _InMemoryLocalOrderStatusStore(
        {"callback-all-sequence-status-001": "submitted"}
    )
    review_source = _BrokerEventOrderStatusReviewSource({f"{report_id}:0002": "filled"})
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=_BrokerEventFillAmendmentSource(
                    {qty_fill_id: amended_qty_fill}
                ),
                local_fill_store=local_fills,
            ),
            RepairActionType.REFRESH_BROKER_ORDER: BrokerRefreshRepairHandler(
                scenario.missing_gateway
            ),
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_all_mismatch_fill_import_source(scenario),
                local_fill_store=local_fills,
            ),
            RepairActionType.REVIEW_ORDER_STATUS: ReviewOrderStatusRepairHandler(
                review_source=review_source,
                local_order_store=local_orders,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:35:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    failed_message = f"amended fill {price_fill_id} was not found"
    assert [result.action_id for result in results] == [
        f"{report_id}:{index:04d}" for index in range(len(plan.actions))
    ]
    assert [result.status for result in results] == [
        "executed",
        "failed",
        "executed",
        "executed",
        "executed",
    ]
    assert results[1].message == failed_message
    assert [action.status for action in workflow_store.list_actions(report_id)] == [
        RepairActionStatus.EXECUTED,
        RepairActionStatus.APPROVED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
    ]
    assert local_fills.get_fill(qty_fill_id) == amended_qty_fill
    assert local_fills.get_fill(price_fill_id) == current_price_fill
    imported_extra_fill = local_fills.get_fill(extra_fill_id)
    assert imported_extra_fill is not None
    assert imported_extra_fill.intent_id == "callback-all-sequence-extra-001"
    assert local_orders.updated == [
        ("callback-all-sequence-status-001", "filled", ("submitted",))
    ]
    assert len(rows) == 5
    assert [
        (
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            "amend_local_fill",
            "callback-all-sequence-qty-001",
            "broker-callback-all-sequence-qty-001",
            qty_fill_id,
            "executed",
            f"amended local fill {qty_fill_id}",
        ),
        (
            "amend_local_fill",
            "callback-all-sequence-price-001",
            "broker-callback-all-sequence-price-001",
            price_fill_id,
            "failed",
            failed_message,
        ),
        (
            "review_order_status",
            "callback-all-sequence-status-001",
            "broker-callback-all-sequence-status-001",
            None,
            "executed",
            "updated local order callback-all-sequence-status-001 status to filled",
        ),
        (
            "refresh_broker_order",
            "callback-all-sequence-missing-001",
            "broker-callback-all-sequence-missing-001",
            None,
            "executed",
            "queried 0 broker fills",
        ),
        (
            "import_broker_fill",
            "callback-all-sequence-extra-001",
            "broker-callback-all-sequence-extra-001",
            extra_fill_id,
            "executed",
            f"imported broker fill {extra_fill_id}",
        ),
    ]


def test_callback_derived_failed_amendment_retry_replays_only_unfinished_repair(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    fixture = _prepare_all_mismatch_retry_replay_fixture(sqlite_client, sqlite_pool)
    first_review_source = _BrokerEventOrderStatusReviewSource(
        {f"{fixture.report_id}:0002": "filled"}
    )
    first_amend_source = _BrokerEventFillAmendmentSource(
        {fixture.qty_fill_id: fixture.amended_qty_fill}
    )
    first_executor = _all_mismatch_repair_executor(
        workflow_store=fixture.workflow_store,
        amendment_source=first_amend_source,
        review_source=first_review_source,
        local_fills=fixture.local_fills,
        local_orders=fixture.local_orders,
        scenario=fixture.scenario,
        audit_service=fixture.audit_service,
        run_id=fixture.run_id,
    )

    first_results = first_executor.execute_report_actions(
        fixture.report_id,
        executed_at="2026-06-01T09:35:00Z",
    )
    rows_after_first = fixture.audit_service.query(
        fixture.run_id,
        record_type="repair_execution",
    )
    first_payloads = [orjson.loads(row["payload"]) for row in rows_after_first]
    first_local_order_updates = list(fixture.local_orders.updated)

    assert [result.status for result in first_results] == [
        "executed",
        "failed",
        "executed",
        "executed",
        "executed",
    ]
    assert [
        action.status
        for action in fixture.workflow_store.list_actions(fixture.report_id)
    ] == [
        RepairActionStatus.EXECUTED,
        RepairActionStatus.APPROVED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
    ]
    assert first_amend_source.requested_fill_ids == [
        fixture.qty_fill_id,
        fixture.price_fill_id,
    ]
    assert first_review_source.requested_action_ids == [f"{fixture.report_id}:0002"]
    assert first_local_order_updates == [
        ("callback-all-sequence-status-001", "filled", ("submitted",))
    ]
    assert fixture.local_fills.get_fill(fixture.qty_fill_id) == fixture.amended_qty_fill
    assert (
        fixture.local_fills.get_fill(fixture.price_fill_id)
        == fixture.current_price_fill
    )
    assert len(rows_after_first) == 5
    assert [
        (payload["action_id"], payload["status"], payload["message"])
        for payload in first_payloads
    ] == [
        (
            f"{fixture.report_id}:0000",
            "executed",
            f"amended local fill {fixture.qty_fill_id}",
        ),
        (
            f"{fixture.report_id}:0001",
            "failed",
            f"amended fill {fixture.price_fill_id} was not found",
        ),
        (
            f"{fixture.report_id}:0002",
            "executed",
            "updated local order callback-all-sequence-status-001 status to filled",
        ),
        (f"{fixture.report_id}:0003", "executed", "queried 0 broker fills"),
        (
            f"{fixture.report_id}:0004",
            "executed",
            f"imported broker fill {fixture.extra_fill_id}",
        ),
    ]

    second_review_source = _BrokerEventOrderStatusReviewSource(
        {f"{fixture.report_id}:0002": "filled"}
    )
    second_amend_source = _BrokerEventFillAmendmentSource(
        {fixture.price_fill_id: fixture.amended_price_fill}
    )
    second_executor = _all_mismatch_repair_executor(
        workflow_store=fixture.workflow_store,
        amendment_source=second_amend_source,
        review_source=second_review_source,
        local_fills=fixture.local_fills,
        local_orders=fixture.local_orders,
        scenario=fixture.scenario,
        audit_service=fixture.audit_service,
        run_id=fixture.run_id,
    )

    second_results = second_executor.execute_report_actions(
        fixture.report_id,
        executed_at="2026-06-01T09:36:00Z",
    )
    rows_after_second = fixture.audit_service.query(
        fixture.run_id,
        record_type="repair_execution",
    )
    new_rows = rows_after_second[len(rows_after_first) :]
    second_payloads = [orjson.loads(row["payload"]) for row in new_rows]

    assert [result.status for result in second_results] == [
        "skipped",
        "executed",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert [
        action.status
        for action in fixture.workflow_store.list_actions(fixture.report_id)
    ] == [
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
    ]
    assert second_amend_source.requested_fill_ids == [fixture.price_fill_id]
    assert second_review_source.requested_action_ids == []
    assert fixture.local_orders.updated == first_local_order_updates
    assert fixture.local_fills.get_fill(fixture.qty_fill_id) == fixture.amended_qty_fill
    assert (
        fixture.local_fills.get_fill(fixture.price_fill_id)
        == fixture.amended_price_fill
    )
    imported_extra_fill = fixture.local_fills.get_fill(fixture.extra_fill_id)
    assert imported_extra_fill is not None
    assert imported_extra_fill.intent_id == "callback-all-sequence-extra-001"
    assert len(rows_after_second) == 10
    assert [
        (
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in second_payloads
    ] == [
        (
            "amend_local_fill",
            "callback-all-sequence-qty-001",
            "broker-callback-all-sequence-qty-001",
            fixture.qty_fill_id,
            "skipped",
            "repair action is executed",
        ),
        (
            "amend_local_fill",
            "callback-all-sequence-price-001",
            "broker-callback-all-sequence-price-001",
            fixture.price_fill_id,
            "executed",
            f"amended local fill {fixture.price_fill_id}",
        ),
        (
            "review_order_status",
            "callback-all-sequence-status-001",
            "broker-callback-all-sequence-status-001",
            None,
            "skipped",
            "repair action is executed",
        ),
        (
            "refresh_broker_order",
            "callback-all-sequence-missing-001",
            "broker-callback-all-sequence-missing-001",
            None,
            "skipped",
            "repair action is executed",
        ),
        (
            "import_broker_fill",
            "callback-all-sequence-extra-001",
            "broker-callback-all-sequence-extra-001",
            fixture.extra_fill_id,
            "skipped",
            "repair action is executed",
        ),
    ]


def test_callback_derived_stale_same_fill_claim_can_be_replaced_across_reports(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-stale-resource-claim-001"
    report_a_id = "rec-callback-stale-resource-claim-a"
    report_b_id = "rec-callback-stale-resource-claim-b"
    sink = InMemoryBrokerEventSink()
    scenario = _submit_all_mismatch_callback_scenario(run_id=run_id, sink=sink)
    plan_a = plan_repair(_all_mismatch_report(report_id=report_a_id, scenario=scenario))
    plan_b = plan_repair(_all_mismatch_report(report_id=report_b_id, scenario=scenario))
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan_a, created_at="2026-06-01T09:32:00Z")
    workflow_store.save_plan(plan_b, created_at="2026-06-01T09:32:01Z")
    _approve_all_mismatch_manual_actions(workflow_store, report_a_id)
    _approve_all_mismatch_manual_actions(workflow_store, report_b_id)
    qty_fill_id = "broker-fill-callback-all-sequence-qty-001"
    current_qty_fill, _ = _current_all_mismatch_fill_records()
    amended_qty_fill = replace(
        current_qty_fill,
        quantity=100,
        notes="amended after stale callback-derived claim replacement",
        created_at="2026-06-01T09:40:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_qty_fill)
    amendment_source = _BrokerEventFillAmendmentSource({qty_fill_id: amended_qty_fill})
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )
    stale_claim = workflow_store.claim_for_execution(
        f"{report_a_id}:0000",
        executor="stalled-repair-worker",
        claimed_at="2026-06-01T09:35:00Z",
    )

    result = executor.execute_action(
        f"{report_b_id}:0000",
        executed_at="2026-06-01T09:40:00Z",
        reclaim_before="2026-06-01T09:36:00Z",
    )
    stale_owner_mark = workflow_store.mark_executed(
        f"{report_a_id}:0000",
        executor="stalled-repair-worker",
        result="late stale amendment",
        executed_at="2026-06-01T09:41:00Z",
    )

    stale_record = workflow_store.get_action(f"{report_a_id}:0000")
    replacement_record = workflow_store.get_action(f"{report_b_id}:0000")
    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert stale_claim is not None
    assert result.status == "executed"
    assert result.message == f"amended local fill {qty_fill_id}"
    assert amendment_source.requested_action_ids == [f"{report_b_id}:0000"]
    assert amendment_source.requested_fill_ids == [qty_fill_id]
    assert local_fills.get_fill(qty_fill_id) == amended_qty_fill
    assert stale_owner_mark is False
    assert stale_record is not None
    assert stale_record.status is RepairActionStatus.APPROVED
    assert stale_record.executor is None
    assert stale_record.claimed_at is None
    assert replacement_record is not None
    assert replacement_record.status is RepairActionStatus.EXECUTED
    assert replacement_record.executor == "repair-worker-b"
    assert replacement_record.execution_result == f"amended local fill {qty_fill_id}"
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_b_id}:0000",
            "amend_local_fill",
            "callback-all-sequence-qty-001",
            "broker-callback-all-sequence-qty-001",
            qty_fill_id,
            "executed",
            f"amended local fill {qty_fill_id}",
        )
    ]


def test_callback_derived_active_same_fill_claim_blocks_later_report_actions(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-active-resource-claim-001"
    report_a_id = "rec-callback-active-resource-claim-a"
    report_b_id = "rec-callback-active-resource-claim-b"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-active-resource-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(run_id, event_type="fill")
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report_a = reconcile(
        report_id=report_a_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.25,
                average_fill_price=10.25,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    report_b = replace(report_a, report_id=report_b_id)
    plan_a = plan_repair(report_a)
    plan_b = plan_repair(report_b)
    fill_id = "broker-fill-callback-active-resource-claim-001"
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan_a, created_at="2026-06-01T09:32:00Z")
    workflow_store.save_plan(plan_b, created_at="2026-06-01T09:32:01Z")
    for action_id in (
        f"{report_a_id}:0000",
        f"{report_b_id}:0000",
        f"{report_b_id}:0001",
    ):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill amendment reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    stale_claim = workflow_store.claim_for_execution(
        f"{report_a_id}:0000",
        executor="active-repair-worker",
        claimed_at="2026-06-01T09:35:00Z",
    )
    amendment_source = _BrokerEventFillAmendmentSource({})
    local_fills = _InMemoryLocalFillStore()
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_b_id,
        executed_at="2026-06-01T09:36:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert stale_claim is not None
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan_b.actions
    ] == [
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            "callback-active-resource-claim-001",
            "broker-callback-active-resource-claim-001",
        ),
        (
            MismatchType.PRICE_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            "callback-active-resource-claim-001",
            "broker-callback-active-resource-claim-001",
        ),
    ]
    assert [result.status for result in results] == ["skipped", "skipped"]
    assert [result.message for result in results] == [
        "repair action is blocked by another in-flight claim",
        f"local fill {fill_id} blocked by earlier in-flight amendment in report",
    ]
    assert amendment_source.requested_action_ids == []
    assert amendment_source.requested_fill_ids == []
    assert [
        workflow_store.get_action(f"{report_b_id}:{index:04d}").status
        for index in range(2)
    ] == [RepairActionStatus.APPROVED, RepairActionStatus.APPROVED]
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_b_id}:0000",
            "amend_local_fill",
            "callback-active-resource-claim-001",
            "broker-callback-active-resource-claim-001",
            fill_id,
            "skipped",
            "repair action is blocked by another in-flight claim",
        ),
        (
            f"{report_b_id}:0001",
            "amend_local_fill",
            "callback-active-resource-claim-001",
            "broker-callback-active-resource-claim-001",
            fill_id,
            "skipped",
            f"local fill {fill_id} blocked by earlier in-flight amendment in report",
        ),
    ]


def test_callback_derived_stale_claim_reclaim_closes_later_same_fill_report_action(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-report-stale-resource-claim-001"
    report_a_id = "rec-callback-report-stale-resource-claim-a"
    report_b_id = "rec-callback-report-stale-resource-claim-b"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-report-stale-resource-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_events = sink.list_broker_events(run_id, event_type="fill")
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report_a = reconcile(
        report_id=report_a_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.25,
                average_fill_price=10.25,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    report_b = replace(report_a, report_id=report_b_id)
    plan_a = plan_repair(report_a)
    plan_b = plan_repair(report_b)
    fill_id = "broker-fill-callback-report-stale-resource-claim-001"
    current_fill = FillRecord(
        fill_id=fill_id,
        intent_id="callback-report-stale-resource-claim-001",
        strategy_id="acct-live-sim",
        trade_date="2026-06-01",
        instrument_id=510300,
        direction="buy",
        quantity=40,
        fill_price=10.0,
        fee=0.0,
        slippage=0.0,
        notes="current callback-derived local fill",
        settlement_date="2026-06-02",
        created_at="2026-06-01T09:34:00Z",
    )
    amended_fill = replace(
        current_fill,
        quantity=100,
        fill_price=10.25,
        notes="amended after report-level stale claim replacement",
        created_at="2026-06-01T09:40:00Z",
    )
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan_a, created_at="2026-06-01T09:32:00Z")
    workflow_store.save_plan(plan_b, created_at="2026-06-01T09:32:01Z")
    for action_id in (
        f"{report_a_id}:0000",
        f"{report_b_id}:0000",
        f"{report_b_id}:0001",
    ):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill amendment reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    stale_claim = workflow_store.claim_for_execution(
        f"{report_a_id}:0000",
        executor="stalled-repair-worker",
        claimed_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_fill)
    amendment_source = _BrokerEventFillAmendmentSource({fill_id: amended_fill})
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_b_id,
        executed_at="2026-06-01T09:40:00Z",
        reclaim_before="2026-06-01T09:36:00Z",
    )
    stale_owner_mark = workflow_store.mark_executed(
        f"{report_a_id}:0000",
        executor="stalled-repair-worker",
        result="late stale amendment",
        executed_at="2026-06-01T09:41:00Z",
    )

    stale_record = workflow_store.get_action(f"{report_a_id}:0000")
    replacement_records = [
        workflow_store.get_action(f"{report_b_id}:{index:04d}") for index in range(2)
    ]
    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert stale_claim is not None
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan_b.actions
    ] == [
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            "callback-report-stale-resource-claim-001",
            "broker-callback-report-stale-resource-claim-001",
        ),
        (
            MismatchType.PRICE_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            "callback-report-stale-resource-claim-001",
            "broker-callback-report-stale-resource-claim-001",
        ),
    ]
    assert [result.status for result in results] == ["executed", "executed"]
    assert [result.message for result in results] == [
        f"amended local fill {fill_id}",
        f"local fill {fill_id} already amended earlier in report",
    ]
    assert [result.effect_count for result in results] == [1, 0]
    assert amendment_source.requested_action_ids == [f"{report_b_id}:0000"]
    assert amendment_source.requested_fill_ids == [fill_id]
    assert local_fills.get_fill(fill_id) == amended_fill
    assert stale_owner_mark is False
    assert stale_record is not None
    assert stale_record.status is RepairActionStatus.APPROVED
    assert stale_record.executor is None
    assert stale_record.claimed_at is None
    assert [record.status for record in replacement_records if record is not None] == [
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
    ]
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_b_id}:0000",
            "amend_local_fill",
            "callback-report-stale-resource-claim-001",
            "broker-callback-report-stale-resource-claim-001",
            fill_id,
            "executed",
            f"amended local fill {fill_id}",
        ),
        (
            f"{report_b_id}:0001",
            "amend_local_fill",
            "callback-report-stale-resource-claim-001",
            "broker-callback-report-stale-resource-claim-001",
            fill_id,
            "executed",
            f"local fill {fill_id} already amended earlier in report",
        ),
    ]


def test_callback_derived_active_import_claim_blocks_later_same_fill_amendment(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-active-import-claim-001"
    report_id = "rec-callback-active-import-claim-001"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-active-import-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_event = sink.list_broker_events(run_id, event_type="fill")[0]
    fill_id = cast(str, fill_event.fill_id)
    order_id = cast(str, fill_event.order_id)
    broker_order_id = cast(str, fill_event.broker_order_id)
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                expected_quantity=100,
                actual_quantity=40,
            ),
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    for action_id in (f"{report_id}:0000", f"{report_id}:0001"):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill local mutation reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    active_import_claim = workflow_store.claim_for_execution(
        f"{report_id}:0000",
        executor="active-import-worker",
        claimed_at="2026-06-01T09:35:00Z",
    )
    amendment_source = _BrokerEventFillAmendmentSource({})
    local_fills = _InMemoryLocalFillStore()
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:36:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    local_mutation_skip_message = (
        f"local fill {fill_id} blocked by earlier in-flight local mutation in report"
    )
    assert active_import_claim is not None
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan.actions
    ] == [
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
    ]
    assert [result.status for result in results] == ["skipped", "skipped"]
    assert [result.message for result in results] == [
        "repair action is executing",
        local_mutation_skip_message,
    ]
    assert amendment_source.requested_action_ids == []
    assert amendment_source.requested_fill_ids == []
    assert local_fills.records == {}
    import_action = workflow_store.get_action(f"{report_id}:0000")
    amendment_action = workflow_store.get_action(f"{report_id}:0001")
    assert import_action is not None
    assert amendment_action is not None
    assert import_action.status is RepairActionStatus.EXECUTING
    assert amendment_action.status is RepairActionStatus.APPROVED
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_id}:0000",
            "import_broker_fill",
            order_id,
            broker_order_id,
            fill_id,
            "skipped",
            "repair action is executing",
        ),
        (
            f"{report_id}:0001",
            "amend_local_fill",
            order_id,
            broker_order_id,
            fill_id,
            "skipped",
            local_mutation_skip_message,
        ),
    ]


def test_callback_derived_failed_import_blocks_later_same_fill_amendment(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-failed-import-claim-001"
    report_id = "rec-callback-failed-import-claim-001"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-failed-import-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_event = sink.list_broker_events(run_id, event_type="fill")[0]
    fill_id = cast(str, fill_event.fill_id)
    order_id = cast(str, fill_event.order_id)
    broker_order_id = cast(str, fill_event.broker_order_id)
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                expected_quantity=100,
                actual_quantity=40,
            ),
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    for action_id in (f"{report_id}:0000", f"{report_id}:0001"):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill local mutation reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    amendment_source = _BrokerEventFillAmendmentSource({})
    local_fills = _InMemoryLocalFillStore()
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_BrokerEventFillImportSource({}),
                local_fill_store=local_fills,
            ),
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:36:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    failed_mutation_skip_message = (
        f"local fill {fill_id} blocked by earlier failed local mutation in report"
    )
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan.actions
    ] == [
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
    ]
    assert [result.status for result in results] == ["failed", "skipped"]
    assert [result.message for result in results] == [
        f"broker fill {fill_id} was not found",
        failed_mutation_skip_message,
    ]
    assert amendment_source.requested_action_ids == []
    assert amendment_source.requested_fill_ids == []
    assert local_fills.records == {}
    assert [
        (
            workflow_store.get_action(f"{report_id}:{index:04d}").status,
            workflow_store.get_action(f"{report_id}:{index:04d}").executor,
        )
        for index in range(2)
    ] == [
        (RepairActionStatus.APPROVED, None),
        (RepairActionStatus.APPROVED, None),
    ]
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_id}:0000",
            "import_broker_fill",
            order_id,
            broker_order_id,
            fill_id,
            "failed",
            f"broker fill {fill_id} was not found",
        ),
        (
            f"{report_id}:0001",
            "amend_local_fill",
            order_id,
            broker_order_id,
            fill_id,
            "skipped",
            failed_mutation_skip_message,
        ),
    ]


def test_callback_derived_failed_amendment_blocks_later_same_fill_import(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-failed-amendment-import-claim-001"
    report_id = "rec-callback-failed-amendment-import-claim-001"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-failed-amendment-import-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_event = sink.list_broker_events(run_id, event_type="fill")[0]
    fill_id = cast(str, fill_event.fill_id)
    order_id = cast(str, fill_event.order_id)
    broker_order_id = cast(str, fill_event.broker_order_id)
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                expected_quantity=100,
                actual_quantity=40,
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
        ),
    )
    plan = plan_repair(report)
    current_fill = FillRecord(
        fill_id=fill_id,
        intent_id=order_id,
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=cast(int, fill_event.instrument_id),
        direction=cast(str, fill_event.payload["direction"]),
        quantity=40,
        fill_price=10.0,
        fee=cast(float, fill_event.payload["fee"]),
        slippage=cast(float, fill_event.payload["slippage"]),
        notes="current local fill before failed amendment",
        created_at=fill_event.event_time,
    )
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    for action_id in (f"{report_id}:0000", f"{report_id}:0001"):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill amendment/import reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    amendment_source = _BrokerEventFillAmendmentSource({})
    import_source = _BrokerEventFillImportSource({(order_id, fill_id): fill_event})
    local_fills = _InMemoryLocalFillStore()
    local_fills.save_fill(current_fill)
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=import_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:36:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    failed_mutation_skip_message = (
        f"local fill {fill_id} blocked by earlier failed amendment in report"
    )
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan.actions
    ] == [
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
    ]
    assert [result.status for result in results] == ["failed", "skipped"]
    assert [result.message for result in results] == [
        f"amended fill {fill_id} was not found",
        failed_mutation_skip_message,
    ]
    assert amendment_source.requested_action_ids == [f"{report_id}:0000"]
    assert amendment_source.requested_fill_ids == [fill_id]
    assert import_source.requested_action_ids == []
    assert import_source.requested_fill_ids == []
    assert local_fills.get_fill(fill_id) == current_fill
    assert [
        (
            workflow_store.get_action(f"{report_id}:{index:04d}").status,
            workflow_store.get_action(f"{report_id}:{index:04d}").executor,
        )
        for index in range(2)
    ] == [
        (RepairActionStatus.APPROVED, None),
        (RepairActionStatus.APPROVED, None),
    ]
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_id}:0000",
            "amend_local_fill",
            order_id,
            broker_order_id,
            fill_id,
            "failed",
            f"amended fill {fill_id} was not found",
        ),
        (
            f"{report_id}:0001",
            "import_broker_fill",
            order_id,
            broker_order_id,
            fill_id,
            "skipped",
            failed_mutation_skip_message,
        ),
    ]


def test_callback_derived_successful_import_allows_later_same_fill_amendment(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-successful-import-claim-001"
    report_id = "rec-callback-successful-import-claim-001"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-successful-import-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_event = sink.list_broker_events(run_id, event_type="fill")[0]
    fill_id = cast(str, fill_event.fill_id)
    order_id = cast(str, fill_event.order_id)
    broker_order_id = cast(str, fill_event.broker_order_id)
    report = ReconciliationReport(
        report_id=report_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                expected_quantity=100,
                actual_quantity=40,
            ),
        ),
    )
    plan = plan_repair(report)
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan, created_at="2026-06-01T09:32:00Z")
    for action_id in (f"{report_id}:0000", f"{report_id}:0001"):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill local mutation reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    imported_fill = FillRecord(
        fill_id=fill_id,
        intent_id=order_id,
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=cast(int, fill_event.instrument_id),
        direction=cast(str, fill_event.payload["direction"]),
        quantity=40,
        fill_price=10.0,
        fee=cast(float, fill_event.payload["fee"]),
        slippage=cast(float, fill_event.payload["slippage"]),
        notes="imported from recorded broker event",
        created_at=fill_event.event_time,
    )
    amended_fill = replace(
        imported_fill,
        quantity=100,
        notes="amended after import in same callback-derived report",
        created_at="2026-06-01T09:36:30Z",
    )
    amendment_source = _BrokerEventFillAmendmentSource({fill_id: amended_fill})
    local_fills = _InMemoryLocalFillStore()
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_BrokerEventFillImportSource(
                    {(order_id, fill_id): fill_event}
                ),
                local_fill_store=local_fills,
            ),
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_id,
        executed_at="2026-06-01T09:36:00Z",
    )

    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    import_action = workflow_store.get_action(f"{report_id}:0000")
    amendment_action = workflow_store.get_action(f"{report_id}:0001")
    assert import_action is not None
    assert amendment_action is not None
    assert [result.status for result in results] == ["executed", "executed"]
    assert [result.message for result in results] == [
        f"imported broker fill {fill_id}",
        f"amended local fill {fill_id}",
    ]
    assert amendment_source.requested_action_ids == [f"{report_id}:0001"]
    assert amendment_source.requested_fill_ids == [fill_id]
    assert local_fills.get_fill(fill_id) == amended_fill
    assert import_action.status is RepairActionStatus.EXECUTED
    assert amendment_action.status is RepairActionStatus.EXECUTED
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_id}:0000",
            "import_broker_fill",
            order_id,
            broker_order_id,
            fill_id,
            "executed",
            f"imported broker fill {fill_id}",
        ),
        (
            f"{report_id}:0001",
            "amend_local_fill",
            order_id,
            broker_order_id,
            fill_id,
            "executed",
            f"amended local fill {fill_id}",
        ),
    ]


def test_callback_derived_stale_import_claim_reclaim_allows_report_amendment(
    sqlite_client: SQLiteClient,
    sqlite_pool: SQLitePool,
) -> None:
    run_id = "run-callback-stale-import-claim-001"
    report_a_id = "rec-callback-stale-import-claim-a"
    report_b_id = "rec-callback-stale-import-claim-b"
    sink = InMemoryBrokerEventSink()
    gateway = BrokerEventRecordingGateway(
        gateway=UniqueFillIdBrokerGateway(fill_quantity=40),
        event_sink=sink,
        run_id=run_id,
        broker="alpha",
        now=SequenceClock(
            *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(8))
        ),
    )
    order = _order("callback-stale-import-claim-001", quantity=100, price=10.0)

    gateway.submit_order(order)

    fill_event = sink.list_broker_events(run_id, event_type="fill")[0]
    fill_id = cast(str, fill_event.fill_id)
    order_id = cast(str, fill_event.order_id)
    broker_order_id = cast(str, fill_event.broker_order_id)
    report_a = ReconciliationReport(
        report_id=report_a_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=0,
        actual_count=1,
        diff_count=1,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
        ),
    )
    report_b = ReconciliationReport(
        report_id=report_b_id,
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected_count=1,
        actual_count=1,
        diff_count=2,
        status="mismatch",
        diffs=(
            ReconciliationDiff(
                mismatch_type=MismatchType.EXTRA_FILL,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                actual_quantity=40,
                actual_price=10.0,
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id=order_id,
                fill_id=fill_id,
                client_order_id=order_id,
                broker_order_id=broker_order_id,
                expected_quantity=100,
                actual_quantity=40,
            ),
        ),
    )
    plan_a = plan_repair(report_a)
    plan_b = plan_repair(report_b)
    imported_fill = FillRecord(
        fill_id=fill_id,
        intent_id=order_id,
        strategy_id="strategy-live-sim",
        trade_date="2026-06-01",
        instrument_id=cast(int, fill_event.instrument_id),
        direction=cast(str, fill_event.payload["direction"]),
        quantity=40,
        fill_price=10.0,
        fee=cast(float, fill_event.payload["fee"]),
        slippage=cast(float, fill_event.payload["slippage"]),
        notes="imported after stale import claim replacement",
        created_at=fill_event.event_time,
    )
    amended_fill = replace(
        imported_fill,
        quantity=100,
        notes="amended after stale import reclaim report continuation",
        created_at="2026-06-01T09:36:30Z",
    )
    workflow_store = SQLiteRepairWorkflowStore(sqlite_client)
    workflow_store.init_schema()
    workflow_store.save_plan(plan_a, created_at="2026-06-01T09:32:00Z")
    workflow_store.save_plan(plan_b, created_at="2026-06-01T09:32:01Z")
    for action_id in (
        f"{report_a_id}:0000",
        f"{report_b_id}:0000",
        f"{report_b_id}:0001",
    ):
        workflow_store.approve_action(
            action_id,
            reviewer="ops",
            reason="same fill import/amendment reviewed",
            reviewed_at="2026-06-01T09:33:00Z",
        )
    stale_import_claim = workflow_store.claim_for_execution(
        f"{report_a_id}:0000",
        executor="stalled-import-worker",
        claimed_at="2026-06-01T09:35:00Z",
    )
    local_fills = _InMemoryLocalFillStore()
    amendment_source = _BrokerEventFillAmendmentSource({fill_id: amended_fill})
    audit_service = ExecutionAuditService(sqlite_pool)
    audit_service.init_schema()
    executor = RepairActionExecutor(
        workflow_store=workflow_store,
        handlers={
            RepairActionType.IMPORT_BROKER_FILL: ImportBrokerFillRepairHandler(
                broker_fill_source=_BrokerEventFillImportSource(
                    {(order_id, fill_id): fill_event}
                ),
                local_fill_store=local_fills,
            ),
            RepairActionType.AMEND_LOCAL_FILL: AmendLocalFillRepairHandler(
                amendment_source=amendment_source,
                local_fill_store=local_fills,
            ),
        },
        audit_sink=ExecutionRepairAuditSink(
            audit_service=audit_service,
            run_id=run_id,
        ),
        executor_id="repair-worker-b",
    )

    results = executor.execute_report_actions(
        report_b_id,
        executed_at="2026-06-01T09:36:00Z",
        reclaim_before="2026-06-01T09:35:30Z",
    )
    stale_owner_mark = workflow_store.mark_executed(
        f"{report_a_id}:0000",
        executor="stalled-import-worker",
        result="late stale import",
        executed_at="2026-06-01T09:37:00Z",
    )

    stale_record = workflow_store.get_action(f"{report_a_id}:0000")
    replacement_records = [
        workflow_store.get_action(f"{report_b_id}:{index:04d}") for index in range(2)
    ]
    rows = audit_service.query(run_id, record_type="repair_execution")
    payloads = [orjson.loads(row["payload"]) for row in rows]
    assert stale_import_claim is not None
    assert [
        (
            action.mismatch_type,
            action.action_type,
            action.fill_id,
            action.client_order_id,
            action.broker_order_id,
        )
        for action in plan_b.actions
    ] == [
        (
            MismatchType.EXTRA_FILL,
            RepairActionType.IMPORT_BROKER_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
        (
            MismatchType.QTY_MISMATCH,
            RepairActionType.AMEND_LOCAL_FILL,
            fill_id,
            order_id,
            broker_order_id,
        ),
    ]
    assert [result.status for result in results] == ["executed", "executed"]
    assert [result.message for result in results] == [
        f"imported broker fill {fill_id}",
        f"amended local fill {fill_id}",
    ]
    assert [result.effect_count for result in results] == [1, 1]
    assert amendment_source.requested_action_ids == [f"{report_b_id}:0001"]
    assert amendment_source.requested_fill_ids == [fill_id]
    assert local_fills.get_fill(fill_id) == amended_fill
    assert stale_owner_mark is False
    assert stale_record is not None
    assert stale_record.status is RepairActionStatus.APPROVED
    assert stale_record.executor is None
    assert stale_record.claimed_at is None
    assert [record.status for record in replacement_records if record is not None] == [
        RepairActionStatus.EXECUTED,
        RepairActionStatus.EXECUTED,
    ]
    assert [
        (
            payload["action_id"],
            payload["action_type"],
            payload["client_order_id"],
            payload["broker_order_id"],
            payload.get("fill_id"),
            payload["status"],
            payload["message"],
        )
        for payload in payloads
    ] == [
        (
            f"{report_b_id}:0000",
            "import_broker_fill",
            order_id,
            broker_order_id,
            fill_id,
            "executed",
            f"imported broker fill {fill_id}",
        ),
        (
            f"{report_b_id}:0001",
            "amend_local_fill",
            order_id,
            broker_order_id,
            fill_id,
            "executed",
            f"amended local fill {fill_id}",
        ),
    ]


def test_multi_broker_recorded_fill_links_survive_reconciliation_repair_plan() -> None:
    sink = InMemoryBrokerEventSink()
    alpha = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-repair-matrix-001",
        broker="alpha",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 30, 3, tzinfo=UTC),
        ),
    )
    beta = BrokerEventRecordingGateway(
        gateway=BrokerAckIdGateway(),
        event_sink=sink,
        run_id="run-callback-repair-matrix-001",
        broker="beta",
        now=SequenceClock(
            datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 1, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 9, 31, 3, tzinfo=UTC),
        ),
    )
    alpha_order = _order("callback-alpha-001", quantity=100, price=10.0)
    beta_order = _order("callback-beta-001", quantity=100, price=10.0)

    alpha.submit_order(alpha_order)
    beta.submit_order(beta_order)

    fill_events = sink.list_broker_events(
        "run-callback-repair-matrix-001",
        event_type="fill",
    )
    broker_order_ids_by_order = {
        cast(str, event.order_id): cast(str, event.broker_order_id)
        for event in fill_events
        if event.order_id == "callback-alpha-001" and event.broker_order_id is not None
    }
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-repair-matrix-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=alpha_order,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            )
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order=broker_order_ids_by_order,
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)

    assert {
        (
            action.mismatch_type,
            action.order_id,
            action.fill_id,
            action.broker_order_id,
        )
        for action in plan.actions
    } == {
        (
            MismatchType.QTY_MISMATCH,
            "callback-alpha-001",
            None,
            "broker-callback-alpha-001",
        ),
        (
            MismatchType.EXTRA_FILL,
            "callback-beta-001",
            "broker-fill-001",
            "broker-callback-beta-001",
        ),
    }


def test_interleaved_multi_broker_scoped_fill_links_drive_repair_plan() -> None:
    sink = InMemoryBrokerEventSink()
    clock = SequenceClock(
        *(datetime(2026, 6, 1, 9, 30, second, tzinfo=UTC) for second in range(20))
    )
    alpha = BrokerEventRecordingGateway(
        gateway=SingleSharedFillIdBrokerGateway(),
        event_sink=sink,
        run_id="run-callback-repair-interleaved-001",
        broker="alpha",
        now=clock,
    )
    beta = BrokerEventRecordingGateway(
        gateway=SingleSharedFillIdBrokerGateway(),
        event_sink=sink,
        run_id="run-callback-repair-interleaved-001",
        broker="beta",
        now=clock,
    )
    alpha_main = _order("callback-alpha-main-001", quantity=100, price=10.0)
    beta_main = _order("callback-beta-main-001", quantity=100, price=10.0)
    alpha_extra = _order("callback-alpha-extra-001", quantity=100, price=10.0)

    alpha.connect()
    beta.connect()
    alpha.submit_order(alpha_main)
    beta.submit_order(beta_main)
    alpha.submit_order(alpha_extra)
    beta.cancel_order(beta_main.order_id)
    beta.get_account()

    events = sink.list_broker_events("run-callback-repair-interleaved-001")
    assert {
        (event.broker, event.event_type, event.order_id, event.status)
        for event in events
    } == {
        ("alpha", "connect", None, "connected"),
        ("beta", "connect", None, "connected"),
        ("alpha", "order_ack", "callback-alpha-main-001", "submitted"),
        ("alpha", "fill", "callback-alpha-main-001", "partially_filled"),
        ("beta", "order_ack", "callback-beta-main-001", "submitted"),
        ("beta", "fill", "callback-beta-main-001", "partially_filled"),
        ("alpha", "order_ack", "callback-alpha-extra-001", "submitted"),
        ("alpha", "fill", "callback-alpha-extra-001", "partially_filled"),
        ("beta", "cancel", "callback-beta-main-001", "accepted"),
        ("beta", "account_update", None, "snapshot"),
    }

    fill_events = [event for event in events if event.event_type == "fill"]
    broker_order_ids_by_order_fill = {
        (cast(str, event.order_id), cast(str, event.fill_id)): cast(
            str,
            event.broker_order_id,
        )
        for event in fill_events
        if event.order_id is not None
        and event.fill_id is not None
        and event.broker_order_id is not None
    }
    report = reconcile(
        report_id="rec-callback-repair-interleaved-001",
        account_id="acct-live-sim",
        trade_date="2026-06-01",
        expected=[
            OrderTicket(
                order=alpha_main,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
            OrderTicket(
                order=beta_main,
                status=OrderStatus.FILLED,
                filled_quantity=100,
                filled_price=10.0,
                average_fill_price=10.0,
            ),
        ],
        actual=[_fill_from_broker_event(event) for event in fill_events],
        broker_order_links=BrokerOrderLinkIndex(
            by_order_fill=broker_order_ids_by_order_fill,
        ),
    )
    plan = plan_repair(report)

    assert {
        (
            action.mismatch_type,
            action.order_id,
            action.fill_id,
            action.broker_order_id,
        )
        for action in plan.actions
    } == {
        (
            MismatchType.QTY_MISMATCH,
            "callback-alpha-main-001",
            None,
            "broker-callback-alpha-main-001",
        ),
        (
            MismatchType.QTY_MISMATCH,
            "callback-beta-main-001",
            None,
            "broker-callback-beta-main-001",
        ),
        (
            MismatchType.EXTRA_FILL,
            "callback-alpha-extra-001",
            "broker-fill-001",
            "broker-callback-alpha-extra-001",
        ),
    }


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
        ("order_ack", "live-003", "submitted"),
        ("fill_query_error", "live-003", "failed"),
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
