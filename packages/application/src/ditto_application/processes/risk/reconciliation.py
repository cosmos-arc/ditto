"""Read-only EOD reconciliation across plans, fills, positions, and RiskGate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from ditto_application.exceptions import AppProcessError

__all__ = [
    "PlannedOrder",
    "ReconciliationFill",
    "ReconciliationInput",
    "ReconciliationReport",
    "reconcile_eod",
]


@dataclass(frozen=True)
class PlannedOrder:
    """One immutable order expected by the EOD execution plan."""

    order_id: str
    instrument_id: int
    direction: str
    quantity: int


@dataclass(frozen=True)
class ReconciliationFill:
    """One effective fill used to rebuild end-of-day positions."""

    fill_id: str
    order_id: str
    instrument_id: int
    direction: str
    quantity: int


@dataclass(frozen=True)
class ReconciliationInput:
    """All three reconciliation layers supplied by application readers."""

    account_id: str
    sleeve_id: str
    trade_date: str
    planned_orders: tuple[PlannedOrder, ...]
    fills: tuple[ReconciliationFill, ...]
    opening_positions: Mapping[int, int]
    actual_positions: Mapping[int, int]
    risk_position_fingerprint: str
    actual_position_fingerprint: str


@dataclass(frozen=True)
class ReconciliationReport:
    """Read-only mismatch report; remediation is intentionally external/manual."""

    account_id: str
    sleeve_id: str
    trade_date: str
    status: str
    differences: tuple[str, ...]
    suggestion_allowed: bool
    alert_idempotency_key: str | None


def reconcile_eod(input_: ReconciliationInput) -> ReconciliationReport:
    """Compare plan/fill, rebuilt/actual, and actual/RiskGate fingerprints."""
    _validate_input(input_)
    differences: list[str] = []
    planned = {order.order_id: order for order in input_.planned_orders}
    filled_quantities: dict[str, int] = {}
    rebuilt = dict(input_.opening_positions)
    for fill in input_.fills:
        order = planned.get(fill.order_id)
        if order is None:
            differences.append(f"unplanned_fill:{fill.order_id}")
        elif (
            order.instrument_id != fill.instrument_id
            or order.direction != fill.direction
        ):
            differences.append(f"fill_order_identity:{fill.fill_id}")
        filled_quantities[fill.order_id] = (
            filled_quantities.get(fill.order_id, 0) + fill.quantity
        )
        sign = 1 if fill.direction == "buy" else -1
        rebuilt[fill.instrument_id] = (
            rebuilt.get(fill.instrument_id, 0) + sign * fill.quantity
        )
    for order in input_.planned_orders:
        filled = filled_quantities.get(order.order_id, 0)
        if filled != order.quantity:
            differences.append(
                f"fill_quantity:{order.order_id}:planned={order.quantity}:filled={filled}"
            )
    for instrument_id in sorted(set(rebuilt) | set(input_.actual_positions)):
        rebuilt_quantity = rebuilt.get(instrument_id, 0)
        actual_quantity = input_.actual_positions.get(instrument_id, 0)
        if rebuilt_quantity != actual_quantity:
            differences.append(
                ":".join(
                    (
                        f"position_quantity:{instrument_id}",
                        f"rebuilt={rebuilt_quantity}",
                        f"actual={actual_quantity}",
                    )
                )
            )
    if input_.risk_position_fingerprint != input_.actual_position_fingerprint:
        differences.append("risk_position_fingerprint")
    stable_differences = tuple(sorted(set(differences)))
    status = "mismatch" if stable_differences else "reconciled"
    return ReconciliationReport(
        account_id=input_.account_id,
        sleeve_id=input_.sleeve_id,
        trade_date=input_.trade_date,
        status=status,
        differences=stable_differences,
        suggestion_allowed=not stable_differences,
        alert_idempotency_key=(
            _alert_key(input_, stable_differences) if stable_differences else None
        ),
    )


def _validate_input(input_: ReconciliationInput) -> None:
    _validate_identity(input_)
    _validate_fingerprints(input_)
    _validate_orders_and_fills(input_)
    _validate_positions(input_)


def _validate_identity(input_: ReconciliationInput) -> None:
    if (
        not input_.account_id.strip()
        or not input_.sleeve_id.strip()
        or not input_.trade_date.strip()
    ):
        raise AppProcessError("reconciliation identity must be complete")
    try:
        date.fromisoformat(input_.trade_date)
    except ValueError:
        raise AppProcessError("trade_date must be an ISO date") from None


def _validate_fingerprints(input_: ReconciliationInput) -> None:
    fingerprints = (
        input_.risk_position_fingerprint,
        input_.actual_position_fingerprint,
    )
    if any(
        not fingerprint.startswith("sha256:") or len(fingerprint) <= len("sha256:")
        for fingerprint in fingerprints
    ):
        raise AppProcessError("position fingerprints must be complete sha256 evidence")


def _validate_orders_and_fills(input_: ReconciliationInput) -> None:
    order_ids = tuple(order.order_id for order in input_.planned_orders)
    fill_ids = tuple(fill.fill_id for fill in input_.fills)
    if len(set(order_ids)) != len(order_ids):
        raise AppProcessError("planned order ids must be unique")
    if len(set(fill_ids)) != len(fill_ids):
        raise AppProcessError("fill ids must be unique")
    for order in input_.planned_orders:
        if not order.order_id.strip():
            raise AppProcessError("planned order ids must be non-empty")
    for fill in input_.fills:
        if not fill.fill_id.strip() or not fill.order_id.strip():
            raise AppProcessError("fill and order ids must be non-empty")
    for item in (*input_.planned_orders, *input_.fills):
        if (
            item.direction not in {"buy", "sell"}
            or type(item.quantity) is not int
            or item.quantity <= 0
        ):
            raise AppProcessError(
                "orders and fills require buy/sell and positive quantity"
            )


def _validate_positions(input_: ReconciliationInput) -> None:
    for name, positions in (
        ("opening", input_.opening_positions),
        ("actual", input_.actual_positions),
    ):
        if any(
            type(quantity) is not int or quantity < 0 for quantity in positions.values()
        ):
            raise AppProcessError(f"{name} positions require non-negative integers")


def _alert_key(input_: ReconciliationInput, differences: tuple[str, ...]) -> str:
    payload = "|".join(
        (
            input_.account_id,
            input_.sleeve_id,
            input_.trade_date,
            *differences,
        )
    )
    return f"reconciliation:{sha256(payload.encode()).hexdigest()}"
