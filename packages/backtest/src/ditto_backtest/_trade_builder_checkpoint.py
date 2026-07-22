"""JSON codec for execution trade-builder checkpoint state."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_execution.trade_builder import (
    FifoOpenEntrySnapshot,
    FlatToFlatAccumulatorSnapshot,
    TradeBuilderStateSnapshot,
    TradeMatchingMethod,
)
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide

from ditto_backtest._checkpoint_codec import (
    finite_float,
    payload_float,
    payload_int,
    payload_mapping,
    payload_optional_str,
    payload_sequence,
    payload_str,
    require_exact_keys,
)

__all__ = ["trade_builder_from_payload", "trade_builder_to_payload"]


def trade_builder_to_payload(state: TradeBuilderStateSnapshot) -> dict[str, object]:
    """Serialize one discriminated trade-builder state without losing floats."""
    payload: dict[str, object] = {
        "counter": state.counter,
        "method": state.method.value,
    }
    if state.method is TradeMatchingMethod.FIFO:
        payload["fifo_open_entries"] = [
            {
                "direction": entry.direction.value,
                "entry_date": entry.entry_date.isoformat(),
                "entry_fee": finite_float(entry.entry_fee, "entry_fee"),
                "entry_order_id": entry.entry_order_id,
                "entry_price": finite_float(entry.entry_price, "entry_price"),
                "instrument_id": int(entry.instrument_id),
                "original_quantity": entry.original_quantity,
                "remaining_quantity": entry.remaining_quantity,
                "trade_id": entry.trade_id,
            }
            for entry in state.fifo_open_entries
        ]
    else:
        payload["flat_to_flat_accumulators"] = [
            _flat_accumulator_to_payload(item)
            for item in state.flat_to_flat_accumulators
        ]
    return payload


def trade_builder_from_payload(
    payload: object,
    *,
    strict: bool,
) -> TradeBuilderStateSnapshot:
    """Decode the matching-method variant, requiring complete V2 members."""
    data = payload_mapping(payload)
    try:
        method = TradeMatchingMethod(payload_str(data, "method"))
    except ValueError:
        raise ValueError("checkpoint trade builder method is unsupported") from None
    counter = payload_int(data, "counter")
    if method is TradeMatchingMethod.FIFO:
        if strict:
            require_exact_keys(
                data,
                ("counter", "fifo_open_entries", "method"),
                subject="trade builder",
            )
        entries = tuple(
            _fifo_entry_from_payload(item, strict=strict)
            for item in payload_sequence(data, "fifo_open_entries")
        )
        _require_unique("FIFO trade IDs", tuple(item.trade_id for item in entries))
        return TradeBuilderStateSnapshot(
            method=method,
            counter=counter,
            fifo_open_entries=entries,
        )
    if strict:
        require_exact_keys(
            data,
            ("counter", "flat_to_flat_accumulators", "method"),
            subject="trade builder",
        )
    accumulators = tuple(
        _flat_accumulator_from_payload(item, strict=strict)
        for item in payload_sequence(data, "flat_to_flat_accumulators")
    )
    _require_unique(
        "flat-to-flat instruments",
        tuple(int(item.instrument_id) for item in accumulators),
    )
    return TradeBuilderStateSnapshot(
        method=method,
        counter=counter,
        flat_to_flat_accumulators=accumulators,
    )


def _fifo_entry_from_payload(
    payload: object,
    *,
    strict: bool,
) -> FifoOpenEntrySnapshot:
    data = payload_mapping(payload)
    if strict:
        require_exact_keys(
            data,
            (
                "direction",
                "entry_date",
                "entry_fee",
                "entry_order_id",
                "entry_price",
                "instrument_id",
                "original_quantity",
                "remaining_quantity",
                "trade_id",
            ),
            subject="FIFO trade builder entry",
        )
    return FifoOpenEntrySnapshot(
        trade_id=payload_str(data, "trade_id"),
        instrument_id=InstrumentId(payload_int(data, "instrument_id")),
        direction=OrderSide(payload_str(data, "direction")),
        entry_date=_payload_date(data, "entry_date"),
        entry_price=payload_float(data, "entry_price"),
        entry_fee=payload_float(data, "entry_fee"),
        original_quantity=payload_int(data, "original_quantity"),
        remaining_quantity=payload_int(data, "remaining_quantity"),
        entry_order_id=payload_str(data, "entry_order_id"),
    )


def _flat_accumulator_to_payload(
    item: FlatToFlatAccumulatorSnapshot,
) -> dict[str, object]:
    return {
        "buy_fees": finite_float(item.buy_fees, "buy_fees"),
        "buy_quantity": item.buy_quantity,
        "buy_total_cost": finite_float(item.buy_total_cost, "buy_total_cost"),
        "entry_order_ids": list(item.entry_order_ids),
        "exit_order_ids": list(item.exit_order_ids),
        "first_entry_date": _optional_date_payload(item.first_entry_date),
        "first_exit_date": _optional_date_payload(item.first_exit_date),
        "instrument_id": int(item.instrument_id),
        "last_entry_date": _optional_date_payload(item.last_entry_date),
        "last_exit_date": _optional_date_payload(item.last_exit_date),
        "net_quantity": item.net_quantity,
        "sell_fees": finite_float(item.sell_fees, "sell_fees"),
        "sell_quantity": item.sell_quantity,
        "sell_total_proceeds": finite_float(
            item.sell_total_proceeds,
            "sell_total_proceeds",
        ),
    }


def _flat_accumulator_from_payload(
    payload: object,
    *,
    strict: bool,
) -> FlatToFlatAccumulatorSnapshot:
    data = payload_mapping(payload)
    if strict:
        require_exact_keys(
            data,
            (
                "buy_fees",
                "buy_quantity",
                "buy_total_cost",
                "entry_order_ids",
                "exit_order_ids",
                "first_entry_date",
                "first_exit_date",
                "instrument_id",
                "last_entry_date",
                "last_exit_date",
                "net_quantity",
                "sell_fees",
                "sell_quantity",
                "sell_total_proceeds",
            ),
            subject="flat-to-flat trade builder accumulator",
        )
    return FlatToFlatAccumulatorSnapshot(
        instrument_id=InstrumentId(payload_int(data, "instrument_id")),
        entry_order_ids=_payload_str_tuple(data, "entry_order_ids"),
        exit_order_ids=_payload_str_tuple(data, "exit_order_ids"),
        net_quantity=payload_int(data, "net_quantity"),
        buy_quantity=payload_int(data, "buy_quantity"),
        buy_total_cost=payload_float(data, "buy_total_cost"),
        buy_fees=payload_float(data, "buy_fees"),
        sell_quantity=payload_int(data, "sell_quantity"),
        sell_total_proceeds=payload_float(data, "sell_total_proceeds"),
        sell_fees=payload_float(data, "sell_fees"),
        first_entry_date=_payload_optional_date(data, "first_entry_date"),
        last_entry_date=_payload_optional_date(data, "last_entry_date"),
        first_exit_date=_payload_optional_date(data, "first_exit_date"),
        last_exit_date=_payload_optional_date(data, "last_exit_date"),
    )


def _payload_str_tuple(data: object, key: str) -> tuple[str, ...]:
    values = payload_sequence(payload_mapping(data), key)
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"checkpoint field {key!r} must contain only strings")
    return cast(tuple[str, ...], values)


def _payload_date(data: object, key: str) -> date:
    value = payload_str(payload_mapping(data), key)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"checkpoint field {key!r} must be an ISO date") from None


def _payload_optional_date(data: object, key: str) -> date | None:
    value = payload_optional_str(payload_mapping(data), key)
    return None if value is None else _payload_date({key: value}, key)


def _optional_date_payload(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _require_unique(name: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"checkpoint {name} must be unique")
