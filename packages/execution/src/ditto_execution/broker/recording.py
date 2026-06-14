"""BrokerGateway wrapper that writes normalized broker events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ditto_kernel.tracing import traced
from ditto_portfolio.accounting import FillEvent
from ditto_portfolio.accounting.account import AccountView

from ditto_execution.broker.contracts import (
    BrokerGateway,
    BrokerGatewayCapability,
    BrokerGatewayDescriptor,
    validate_broker_gateway_descriptor,
)
from ditto_execution.models import (
    STANDARD_BROKER_EVENT_TYPES,
    BrokerEventRecord,
    BrokerEventType,
    require_standard_broker_event_type,
)
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket

__all__ = ["BrokerEventRecordingGateway", "BrokerEventSink"]


class BrokerEventSink(Protocol):
    """Sink for normalized broker events."""

    def save_broker_event(self, record: BrokerEventRecord) -> None:
        """Persist one normalized broker event."""
        ...

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
        """Return recorded broker events for durable link-key recovery."""
        ...


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True)
class _BrokerEventDraft:
    event_type: BrokerEventType
    event_time: str
    status: str
    payload: dict[str, object]
    order_id: str | None = None
    broker_order_id: str | None = None
    fill_id: str | None = None
    instrument_id: int | None = None
    correlation_id: str | None = None
    event_id_suffix: str | None = None


@dataclass
class BrokerEventRecordingGateway:
    """
    Decorate a BrokerGateway and persist normalized broker events.

    The wrapper keeps broker operations protocol-preserving. Any concrete
    gateway can be wrapped at composition-root time and prove its event
    semantics through the same conformance tests as paper gateways.
    """

    gateway: BrokerGateway
    event_sink: BrokerEventSink
    run_id: str
    broker: str
    now: Callable[[], datetime] = _utc_now
    broker_order_id_lookup: Callable[[str], str | None] | None = None
    _broker_order_ids: dict[str, str] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
        hash=False,
    )

    def describe(self) -> BrokerGatewayDescriptor:
        """Return the wrapped gateway descriptor plus recording capabilities."""
        underlying = validate_broker_gateway_descriptor(self.gateway.describe())
        recording_capabilities: frozenset[BrokerGatewayCapability] = frozenset(
            {"event_recording", "broker_order_id_recovery"}
        )
        return BrokerGatewayDescriptor(
            gateway_id=f"recording:{underlying.gateway_id}",
            mode="recording",
            capabilities=underlying.capabilities | recording_capabilities,
            supported_event_types=STANDARD_BROKER_EVENT_TYPES,
            notes=(
                *underlying.notes,
                "Records normalized broker events without implementing a real adapter.",
            ),
        )

    @traced("execution.broker.connect")
    def connect(self) -> None:
        """Connect the underlying gateway and record the connection event."""
        self.gateway.connect()
        event_time = self._now_iso()
        self._save_event(
            _BrokerEventDraft(
                event_type="connect",
                event_time=event_time,
                status="connected",
                correlation_id=self.run_id,
                event_id_suffix=self._time_scoped_event_id_suffix(
                    event_type="connect",
                    event_time=event_time,
                ),
                payload={"connected": True},
            )
        )

    @traced("execution.broker.get_account")
    def get_account(self) -> AccountView:
        """Return the underlying gateway account snapshot."""
        account = self.gateway.get_account()
        self._record_account_update(account)
        return account

    @traced("execution.broker.submit_order")
    def submit_order(self, order: Order) -> OrderTicket:
        """Submit an order and record acknowledgement plus opportunistic fills."""
        ticket = self.gateway.submit_order(order)
        self._record_order_ack(order=order, ticket=ticket)
        try:
            fills = self.gateway.query_fills(order.order_id)
        except Exception as exc:
            self._record_fill_query_error(order_id=order.order_id, error=exc)
        else:
            self._record_fills(fills)
        return ticket

    @traced("execution.broker.cancel_order")
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order and record the broker response."""
        try:
            accepted = self.gateway.cancel_order(order_id)
        except Exception as exc:
            broker_order_id = self._broker_order_id(order_id)
            self._record_response_error(
                event_type="cancel",
                order_id=order_id,
                broker_order_id=broker_order_id,
                error=exc,
            )
            raise
        broker_order_id = self._broker_order_id(order_id)
        event_time = self._now_iso()
        status = "accepted" if accepted else "rejected"
        self._save_event(
            _BrokerEventDraft(
                event_type="cancel",
                event_time=event_time,
                order_id=order_id,
                broker_order_id=broker_order_id,
                status=status,
                correlation_id=order_id,
                event_id_suffix=self._attempt_event_id_suffix(
                    event_type="cancel",
                    order_id=order_id,
                    status=status,
                    event_time=event_time,
                ),
                payload=self._with_broker_order_id(
                    {"accepted": accepted},
                    broker_order_id,
                ),
            )
        )
        return accepted

    def reject_order(self, order_id: str, reason: str) -> bool:
        """Reject an order and record the broker response."""
        try:
            accepted = self.gateway.reject_order(order_id, reason)
        except Exception as exc:
            broker_order_id = self._broker_order_id(order_id)
            self._record_response_error(
                event_type="reject",
                order_id=order_id,
                broker_order_id=broker_order_id,
                error=exc,
                payload={"reason": reason},
            )
            raise
        broker_order_id = self._broker_order_id(order_id)
        event_time = self._now_iso()
        status = "rejected" if accepted else "not_found"
        self._save_event(
            _BrokerEventDraft(
                event_type="reject",
                event_time=event_time,
                order_id=order_id,
                broker_order_id=broker_order_id,
                status=status,
                correlation_id=order_id,
                event_id_suffix=self._attempt_event_id_suffix(
                    event_type="reject",
                    order_id=order_id,
                    status=status,
                    event_time=event_time,
                ),
                payload=self._with_broker_order_id(
                    {"accepted": accepted, "reason": reason},
                    broker_order_id,
                ),
            )
        )
        return accepted

    @traced("execution.broker.query_fills")
    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """Query broker fills and record deterministic fill events."""
        try:
            fills = self.gateway.query_fills(order_id)
        except Exception as exc:
            self._record_fill_query_error(order_id=order_id, error=exc)
            raise
        self._record_fills(fills)
        return fills

    def _record_order_ack(self, *, order: Order, ticket: OrderTicket) -> None:
        status = ticket.status.value
        broker_order_id = ticket.broker_order_id
        if self._is_missing_broker_order_id(broker_order_id):
            broker_order_id = self._broker_order_id(order.order_id)
        self._remember_broker_order_id(order.order_id, broker_order_id)
        event_time = self._now_iso()
        self._save_event(
            _BrokerEventDraft(
                event_type="order_ack",
                event_time=event_time,
                order_id=order.order_id,
                broker_order_id=broker_order_id,
                instrument_id=int(order.instrument_id),
                status=status,
                correlation_id=order.order_id,
                event_id_suffix=self._collision_safe_event_id_suffix(
                    base_suffix=f"order_ack:{order.order_id}:{status}",
                    event_type="order_ack",
                    order_id=order.order_id,
                ),
                payload=self._with_broker_order_id(
                    {
                        "order_id": order.order_id,
                        "instrument_id": int(order.instrument_id),
                        "order_type": order.order_type.value,
                        "direction": order.direction.value,
                        "quantity": order.quantity,
                        "price": order.price,
                        "status": status,
                        "filled_quantity": ticket.filled_quantity,
                        "leaves_quantity": ticket.leaves_quantity,
                        "average_fill_price": ticket.average_fill_price,
                    },
                    broker_order_id,
                ),
            )
        )

    def _record_fills(self, fills: tuple[FillEvent, ...]) -> None:
        for fill in fills:
            broker_order_id = self._broker_order_id(fill.order_id)
            self._save_event(
                _BrokerEventDraft(
                    event_type="fill",
                    event_time=self._datetime_iso(fill.event_time),
                    order_id=fill.order_id,
                    broker_order_id=broker_order_id,
                    fill_id=fill.fill_id,
                    instrument_id=int(fill.instrument_id),
                    status=self._fill_status(fill),
                    correlation_id=fill.order_id,
                    event_id_suffix=self._fill_event_id_suffix(
                        fill,
                        broker_order_id=broker_order_id,
                    ),
                    payload=self._with_broker_order_id(
                        {
                            "fill_id": fill.fill_id,
                            "order_id": fill.order_id,
                            "instrument_id": int(fill.instrument_id),
                            "direction": fill.direction.value,
                            "filled_quantity": fill.filled_quantity,
                            "fill_price": fill.fill_price,
                            "fee": fill.fee,
                            "slippage": fill.slippage,
                            "cumulative_quantity": fill.cumulative_quantity,
                            "leaves_quantity": fill.leaves_quantity,
                        },
                        broker_order_id,
                    ),
                )
            )

    def _record_account_update(self, account: AccountView) -> None:
        event_time = self._now_iso()
        self._save_event(
            _BrokerEventDraft(
                event_type="account_update",
                event_time=event_time,
                status="snapshot",
                correlation_id=self.run_id,
                event_id_suffix=self._time_scoped_event_id_suffix(
                    event_type="account_update",
                    event_time=event_time,
                ),
                payload={
                    "cash_available": account.cash.available,
                    "cash_settled": account.cash.settled,
                    "cash_frozen": account.cash.frozen,
                    "cash_total": account.cash.total,
                    "total_value": account.total_value,
                    "nav": account.nav,
                    "exposure": account.exposure,
                    "position_count": len(account.positions),
                },
            )
        )

    def _record_fill_query_error(self, *, order_id: str, error: Exception) -> None:
        broker_order_id = self._broker_order_id(order_id)
        event_time = self._now_iso()
        self._save_event(
            _BrokerEventDraft(
                event_type="fill_query_error",
                event_time=event_time,
                order_id=order_id,
                broker_order_id=broker_order_id,
                status="failed",
                correlation_id=order_id,
                event_id_suffix=self._attempt_event_id_suffix(
                    event_type="fill_query_error",
                    order_id=order_id,
                    status="failed",
                    event_time=event_time,
                ),
                payload=self._with_broker_order_id(
                    {
                        "order_id": order_id,
                        "error_type": type(error).__name__,
                        "message": str(error),
                    },
                    broker_order_id,
                ),
            )
        )

    def _record_response_error(
        self,
        *,
        event_type: BrokerEventType,
        order_id: str,
        broker_order_id: str | None,
        error: Exception,
        payload: dict[str, object] | None = None,
    ) -> None:
        event_time = self._now_iso()
        error_payload: dict[str, object] = {
            "order_id": order_id,
            "error_type": type(error).__name__,
            "message": str(error),
        }
        if payload is not None:
            error_payload.update(payload)
        self._save_event(
            _BrokerEventDraft(
                event_type=event_type,
                event_time=event_time,
                order_id=order_id,
                broker_order_id=broker_order_id,
                status="failed",
                correlation_id=order_id,
                event_id_suffix=self._attempt_event_id_suffix(
                    event_type=event_type,
                    order_id=order_id,
                    status="failed",
                    event_time=event_time,
                ),
                payload=self._with_broker_order_id(error_payload, broker_order_id),
            )
        )

    def _save_event(self, draft: _BrokerEventDraft) -> None:
        event_type = require_standard_broker_event_type(draft.event_type)
        suffix = draft.event_id_suffix or self._event_id_suffix(
            event_type=event_type,
            order_id=draft.order_id,
            fill_id=draft.fill_id,
            status=draft.status,
        )
        self.event_sink.save_broker_event(
            BrokerEventRecord(
                event_id=f"{self.run_id}:{self.broker}:{suffix}",
                run_id=self.run_id,
                broker=self.broker,
                event_type=event_type,
                event_time=draft.event_time,
                order_id=draft.order_id,
                broker_order_id=draft.broker_order_id,
                fill_id=draft.fill_id,
                instrument_id=draft.instrument_id,
                status=draft.status,
                correlation_id=draft.correlation_id,
                payload=draft.payload,
                created_at=self._now_iso(),
            )
        )

    @staticmethod
    def _event_id_suffix(
        *,
        event_type: BrokerEventType,
        order_id: str | None,
        fill_id: str | None,
        status: str,
    ) -> str:
        if fill_id is not None:
            return f"{event_type}:{fill_id}"
        if order_id is not None:
            return f"{event_type}:{order_id}:{status}"
        return f"{event_type}:{status}"

    def _attempt_event_id_suffix(
        self,
        *,
        event_type: BrokerEventType,
        order_id: str,
        status: str,
        event_time: str,
    ) -> str:
        base_suffix = f"{event_type}:{order_id}:{status}:{event_time}"
        return self._collision_safe_event_id_suffix(
            base_suffix=base_suffix,
            event_type=event_type,
            order_id=order_id,
        )

    def _time_scoped_event_id_suffix(self, *, event_type: str, event_time: str) -> str:
        event_type = require_standard_broker_event_type(event_type)
        base_suffix = f"{event_type}:{event_time}"
        return self._collision_safe_event_id_suffix(
            base_suffix=base_suffix,
            event_type=event_type,
        )

    def _collision_safe_event_id_suffix(
        self,
        *,
        base_suffix: str,
        event_type: BrokerEventType,
        order_id: str | None = None,
    ) -> str:
        existing_event_ids = {
            event.event_id
            for event in self.event_sink.list_broker_events(
                self.run_id,
                event_type=event_type,
                order_id=order_id,
            )
        }
        base_event_id = f"{self.run_id}:{self.broker}:{base_suffix}"
        if base_event_id not in existing_event_ids:
            return base_suffix
        attempt = 2
        while f"{base_event_id}:attempt-{attempt}" in existing_event_ids:
            attempt += 1
        return f"{base_suffix}:attempt-{attempt}"

    def _fill_event_id_suffix(
        self,
        fill: FillEvent,
        *,
        broker_order_id: str | None,
    ) -> str:
        base_suffix = (
            f"fill:{fill.order_id}:{fill.fill_id}:"
            f"{fill.cumulative_quantity}:{fill.leaves_quantity}"
        )
        existing_events = {
            event.event_id: event
            for event in self.event_sink.list_broker_events(
                self.run_id,
                event_type="fill",
                order_id=fill.order_id,
                fill_id=fill.fill_id,
            )
        }
        base_event_id = f"{self.run_id}:{self.broker}:{base_suffix}"
        existing = existing_events.get(base_event_id)
        if existing is None:
            return base_suffix
        if self._recorded_fill_matches(
            fill=fill,
            event=existing,
            broker_order_id=broker_order_id,
        ):
            return base_suffix

        revision = 2
        while True:
            revision_event_id = f"{base_event_id}:revision-{revision}"
            existing_revision = existing_events.get(revision_event_id)
            if existing_revision is None:
                return f"{base_suffix}:revision-{revision}"
            if self._recorded_fill_matches(
                fill=fill,
                event=existing_revision,
                broker_order_id=broker_order_id,
            ):
                return f"{base_suffix}:revision-{revision}"
            revision += 1

    def _recorded_fill_matches(
        self,
        *,
        fill: FillEvent,
        event: BrokerEventRecord,
        broker_order_id: str | None,
    ) -> bool:
        payload = event.payload
        fill_facts_match = (
            event.event_time == self._datetime_iso(fill.event_time)
            and event.instrument_id == int(fill.instrument_id)
            and event.status == self._fill_status(fill)
            and payload.get("direction") == fill.direction.value
            and payload.get("filled_quantity") == fill.filled_quantity
            and payload.get("fill_price") == fill.fill_price
            and payload.get("fee") == fill.fee
            and payload.get("slippage") == fill.slippage
            and payload.get("cumulative_quantity") == fill.cumulative_quantity
            and payload.get("leaves_quantity") == fill.leaves_quantity
        )
        if not fill_facts_match:
            return False
        return self._recorded_broker_order_id_matches(
            event=event,
            broker_order_id=broker_order_id,
        )

    def _recorded_broker_order_id_matches(
        self,
        *,
        event: BrokerEventRecord,
        broker_order_id: str | None,
    ) -> bool:
        recorded_broker_order_id = self._recorded_broker_order_id(event)
        if self._is_missing_broker_order_id(recorded_broker_order_id):
            return True
        if self._is_missing_broker_order_id(broker_order_id):
            return True
        return recorded_broker_order_id == broker_order_id

    def _recorded_broker_order_id(
        self,
        event: BrokerEventRecord,
    ) -> str | None:
        if not self._is_missing_broker_order_id(event.broker_order_id):
            return event.broker_order_id
        payload_value = event.payload.get("broker_order_id")
        if isinstance(payload_value, str) and not self._is_missing_broker_order_id(
            payload_value
        ):
            return payload_value
        return None

    @staticmethod
    def _fill_status(fill: FillEvent) -> str:
        if fill.leaves_quantity == 0:
            return "filled"
        return "partially_filled"

    def _now_iso(self) -> str:
        return self._datetime_iso(self.now())

    @staticmethod
    def _datetime_iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    def _broker_order_id(self, order_id: str | None) -> str | None:
        if order_id is None:
            return None
        cached = self._broker_order_ids.get(order_id)
        if cached is not None:
            return cached
        if self.broker_order_id_lookup is None:
            broker_order_id = self._broker_order_id_from_recorded_events(order_id)
        else:
            broker_order_id = self.broker_order_id_lookup(order_id)
            if self._is_missing_broker_order_id(broker_order_id):
                broker_order_id = self._broker_order_id_from_recorded_events(order_id)
        self._remember_broker_order_id(order_id, broker_order_id)
        return broker_order_id

    @staticmethod
    def _is_missing_broker_order_id(value: str | None) -> bool:
        return value is None or not value.strip()

    def _broker_order_id_from_recorded_events(self, order_id: str) -> str | None:
        events = self.event_sink.list_broker_events(
            self.run_id,
            event_type="order_ack",
            order_id=order_id,
        )
        for event in reversed(events):
            if event.broker != self.broker:
                continue
            broker_order_id = self._recorded_broker_order_id(event)
            if broker_order_id is not None:
                return broker_order_id
        return None

    def _remember_broker_order_id(
        self,
        order_id: str,
        broker_order_id: str | None,
    ) -> None:
        if broker_order_id is None:
            return
        if not broker_order_id.strip():
            return
        self._broker_order_ids[order_id] = broker_order_id

    @staticmethod
    def _with_broker_order_id(
        payload: dict[str, object],
        broker_order_id: str | None,
    ) -> dict[str, object]:
        if broker_order_id is None:
            return payload
        return {**payload, "broker_order_id": broker_order_id}
