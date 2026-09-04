"""Deterministic full-replay projections for PAPER and MANUAL account events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from ditto_kernel.identity import InstrumentId

from ditto_portfolio.account_ledger import (
    LEDGER_BUSINESS_TYPES as _BUSINESS_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_CASH_IN_TYPES as _CASH_IN_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_CASH_OUT_TYPES as _CASH_OUT_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_CORPORATE_ACTION_TYPES as _CORPORATE_ACTION_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_POSITION_IN_TYPES as _POSITION_IN_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_POSITION_OUT_TYPES as _POSITION_OUT_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_TRADE_TYPES as _TRADE_TYPES,
)
from ditto_portfolio.account_ledger import (
    LEDGER_ZERO as _ZERO,
)
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventType,
    AccountKind,
    AccountLedgerError,
)
from ditto_portfolio.account_ledger import (
    ledger_event_hash as _event_hash,
)
from ditto_portfolio.account_ledger import (
    ledger_event_values as _event_values,
)
from ditto_portfolio.account_ledger import (
    ledger_hash as _ledger_hash,
)
from ditto_portfolio.account_ledger import (
    ledger_money as _money,
)
from ditto_portfolio.account_ledger import (
    ledger_parse_date as _parse_date,
)
from ditto_portfolio.account_ledger import (
    ledger_price as _price,
)
from ditto_portfolio.account_ledger import (
    ledger_quantity as _quantity,
)

__all__ = [
    "AccountLedgerRebuilder",
    "CashSnapshot",
    "PortfolioPositionSnapshot",
    "PortfolioSnapshot",
]


@dataclass(frozen=True, kw_only=True)
class CashSnapshot:
    """Money-precise cash projection."""

    available: Decimal
    settled: Decimal
    frozen: Decimal = _ZERO

    @property
    def total(self) -> Decimal:
        """Return available plus frozen cash."""
        return _money(self.available + self.frozen)


@dataclass(frozen=True, kw_only=True)
class PortfolioPositionSnapshot:
    """Money- and quantity-precise projected holding."""

    instrument_id: InstrumentId
    quantity: Decimal
    available_quantity: Decimal
    average_cost: Decimal
    last_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal


@dataclass(frozen=True, kw_only=True)
class PortfolioSnapshot:
    """One account projection reconstructed from its complete event stream."""

    account_id: str
    account_kind: AccountKind
    as_of: str
    currency: str
    cash: CashSnapshot
    positions: tuple[PortfolioPositionSnapshot, ...]
    total_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    event_count: int
    ledger_hash: str
    valuation_complete: bool

    def position(self, instrument_id: InstrumentId) -> PortfolioPositionSnapshot:
        """Return one projected holding or fail closed."""
        for position in self.positions:
            if position.instrument_id == instrument_id:
                return position
        raise AccountLedgerError(f"position not found: {instrument_id}")


@dataclass
class _PositionState:
    quantity: Decimal = _ZERO
    available_quantity: Decimal = _ZERO
    average_cost: Decimal = _ZERO
    realized_pnl: Decimal = _ZERO
    total_fees: Decimal = _ZERO


@dataclass
class _ProjectionState:
    available_cash: Decimal
    settled_cash: Decimal
    positions: dict[InstrumentId, _PositionState]
    realized_pnl: Decimal = _ZERO
    total_fees: Decimal = _ZERO


class AccountLedgerRebuilder:
    """Pure, deterministic full replay for PAPER or MANUAL account events."""

    def rebuild(
        self,
        *,
        account: AccountDefinition,
        events: Iterable[AccountEvent],
        as_of: str,
        valuation_prices: Mapping[InstrumentId, Decimal] | None = None,
    ) -> PortfolioSnapshot:
        """Replay all visible events into one immutable snapshot."""
        _parse_date(as_of, "as_of")
        retained = tuple(event for event in events if event.trade_date <= as_of)
        self._validate_stream(account, retained)
        active, replacements = self._resolve_controls(retained)
        projection = _ProjectionState(
            available_cash=_ZERO,
            settled_cash=_ZERO,
            positions={},
        )
        for event in retained:
            if event.event_type in {
                AccountEventType.CORRECTION,
                AccountEventType.REVERSAL,
            }:
                continue
            replacement = replacements.get(event.event_id)
            if replacement is not None:
                self._apply(
                    replacement,
                    replacement.replacement_event_type,
                    projection,
                    as_of,
                )
            elif event.event_id in active:
                self._apply(event, event.event_type, projection, as_of)

        prices = valuation_prices or {}
        valuation_complete = all(
            instrument_id in prices for instrument_id in projection.positions
        )
        projected_positions: list[PortfolioPositionSnapshot] = []
        for instrument_id, state in sorted(
            projection.positions.items(),
            key=lambda item: int(item[0]),
        ):
            last_price = _price(prices.get(instrument_id, state.average_cost))
            market_value = _money(last_price * state.quantity)
            unrealized = _money((last_price - state.average_cost) * state.quantity)
            projected_positions.append(
                PortfolioPositionSnapshot(
                    instrument_id=instrument_id,
                    quantity=_quantity(state.quantity),
                    available_quantity=_quantity(state.available_quantity),
                    average_cost=_price(state.average_cost),
                    last_price=last_price,
                    market_value=market_value,
                    realized_pnl=_money(state.realized_pnl),
                    unrealized_pnl=unrealized,
                    total_fees=_money(state.total_fees),
                )
            )
        positions_tuple = tuple(projected_positions)
        total_value = _money(
            projection.available_cash
            + sum((position.market_value for position in positions_tuple), _ZERO)
        )
        return PortfolioSnapshot(
            account_id=account.account_id,
            account_kind=account.kind,
            as_of=as_of,
            currency=account.currency,
            cash=CashSnapshot(
                available=_money(projection.available_cash),
                settled=_money(projection.settled_cash),
                frozen=_ZERO,
            ),
            positions=positions_tuple,
            total_value=total_value,
            realized_pnl=_money(projection.realized_pnl),
            unrealized_pnl=_money(
                sum((position.unrealized_pnl for position in positions_tuple), _ZERO)
            ),
            total_fees=_money(projection.total_fees),
            event_count=len(retained),
            ledger_hash=_ledger_hash(retained),
            valuation_complete=valuation_complete,
        )

    @staticmethod
    def _validate_stream(
        account: AccountDefinition,
        events: tuple[AccountEvent, ...],
    ) -> None:
        event_ids: set[str] = set()
        idempotency_keys: set[str] = set()
        prior: dict[str, AccountEvent] = {}
        for event in events:
            account.assert_accepts(event)
            if event.event_id in event_ids:
                raise AccountLedgerError(f"duplicate event_id: {event.event_id}")
            if event.idempotency_key in idempotency_keys:
                raise AccountLedgerError(
                    f"duplicate idempotency_key: {event.idempotency_key}"
                )
            if event.event_hash != _event_hash(_event_values(event)):
                raise AccountLedgerError(f"event hash mismatch: {event.event_id}")
            target_id = event.reverses_event_id or event.corrects_event_id
            if target_id is not None:
                target = prior.get(target_id)
                if target is None:
                    raise AccountLedgerError(
                        f"event references unknown prior event: {target_id}"
                    )
                if (
                    event.event_type is AccountEventType.CORRECTION
                    and target.event_type
                    in {AccountEventType.CORRECTION, AccountEventType.REVERSAL}
                ):
                    raise AccountLedgerError(
                        "correction target must be a prior business event"
                    )
            event_ids.add(event.event_id)
            idempotency_keys.add(event.idempotency_key)
            prior[event.event_id] = event

    @staticmethod
    def _resolve_controls(
        events: tuple[AccountEvent, ...],
    ) -> tuple[set[str], dict[str, AccountEvent]]:
        suppressed: set[str] = set()
        replacements: dict[str, AccountEvent] = {}
        for event in reversed(events):
            if event.event_id in suppressed:
                continue
            if event.event_type is AccountEventType.REVERSAL:
                if event.reverses_event_id is not None:
                    suppressed.add(event.reverses_event_id)
            elif (
                event.event_type is AccountEventType.CORRECTION
                and event.corrects_event_id is not None
            ):
                suppressed.add(event.corrects_event_id)
                replacements[event.corrects_event_id] = event
        active = {
            event.event_id for event in events if event.event_id not in suppressed
        }
        return active, replacements

    @staticmethod
    def _apply(
        event: AccountEvent,
        effective_type: AccountEventType | None,
        state: _ProjectionState,
        as_of: str,
    ) -> None:
        if effective_type is None or effective_type not in _BUSINESS_TYPES:
            raise AccountLedgerError("event has no applicable business type")
        if effective_type in _CASH_IN_TYPES | _CASH_OUT_TYPES | _TRADE_TYPES:
            state.available_cash = _money(state.available_cash + event.net_cash)
            if event.settlement_date <= as_of:
                state.settled_cash = _money(state.settled_cash + event.net_cash)
        if effective_type in _TRADE_TYPES:
            state.total_fees = _money(state.total_fees + event.fees + event.tax)
        elif effective_type in {AccountEventType.FEE, AccountEventType.TAX}:
            state.total_fees = _money(
                state.total_fees + event.gross_amount + event.fees + event.tax
            )
        if effective_type in _TRADE_TYPES | _POSITION_IN_TYPES | _POSITION_OUT_TYPES:
            state.realized_pnl = _money(
                state.realized_pnl
                + _apply_position_event(
                    event,
                    effective_type,
                    state.positions,
                    as_of,
                )
            )
        elif effective_type in _CORPORATE_ACTION_TYPES:
            _apply_corporate_action(event, effective_type, state.positions, as_of)


def _apply_position_event(
    event: AccountEvent,
    effective_type: AccountEventType,
    positions: dict[InstrumentId, _PositionState],
    as_of: str,
) -> Decimal:
    instrument_id = event.instrument_id
    if instrument_id is None:
        raise AccountLedgerError("position event requires instrument_id")
    state = positions.get(instrument_id, _PositionState())
    inflow_types = {
        AccountEventType.BUY,
        AccountEventType.OPENING_POSITION,
        AccountEventType.TRANSFER_IN,
    }
    if effective_type in inflow_types:
        _apply_position_inflow(
            event,
            effective_type,
            instrument_id,
            state,
            positions,
            as_of,
        )
        return _ZERO
    if event.quantity > state.available_quantity:
        message = f"insufficient available position for {effective_type.value}:" + (
            f" {instrument_id}"
        )
        raise AccountLedgerError(message)
    remaining = _quantity(state.quantity - event.quantity)
    remaining_available = _quantity(state.available_quantity - event.quantity)
    realized = state.realized_pnl
    realized_delta = _ZERO
    if effective_type is AccountEventType.SELL:
        realized_delta = _money(
            event.gross_amount
            - event.fees
            - event.tax
            - state.average_cost * event.quantity
        )
        realized = _money(realized + realized_delta)
    if remaining == _ZERO:
        positions.pop(instrument_id, None)
        return realized_delta
    positions[instrument_id] = _PositionState(
        quantity=remaining,
        available_quantity=remaining_available,
        average_cost=state.average_cost,
        realized_pnl=realized,
        total_fees=_money(state.total_fees + event.fees + event.tax),
    )
    return realized_delta


def _apply_position_inflow(
    event: AccountEvent,
    effective_type: AccountEventType,
    instrument_id: InstrumentId,
    state: _PositionState,
    positions: dict[InstrumentId, _PositionState],
    as_of: str,
) -> None:
    total_quantity = _quantity(state.quantity + event.quantity)
    acquisition_cost = event.gross_amount
    if effective_type is AccountEventType.BUY:
        acquisition_cost = _money(acquisition_cost + event.fees + event.tax)
    total_cost = state.average_cost * state.quantity + acquisition_cost
    positions[instrument_id] = _PositionState(
        quantity=total_quantity,
        available_quantity=_quantity(
            state.available_quantity
            + (event.quantity if event.settlement_date <= as_of else _ZERO)
        ),
        average_cost=_price(total_cost / total_quantity),
        realized_pnl=state.realized_pnl,
        total_fees=_money(state.total_fees + event.fees + event.tax),
    )


def _apply_corporate_action(
    event: AccountEvent,
    effective_type: AccountEventType,
    positions: dict[InstrumentId, _PositionState],
    as_of: str,
) -> None:
    instrument_id = event.instrument_id
    if instrument_id is None:
        raise AccountLedgerError("corporate action requires instrument_id")
    state = positions.get(instrument_id)
    if state is None:
        raise AccountLedgerError(
            f"corporate action position not found: {instrument_id}"
        )
    direction = (
        Decimal("-1") if effective_type is AccountEventType.MERGE else Decimal("1")
    )
    new_quantity = _quantity(state.quantity + direction * event.quantity)
    available_change = (
        direction * event.quantity if event.settlement_date <= as_of else _ZERO
    )
    new_available_quantity = _quantity(state.available_quantity + available_change)
    if new_quantity <= _ZERO:
        raise AccountLedgerError("corporate action must leave positive quantity")
    if new_available_quantity < _ZERO:
        raise AccountLedgerError("corporate action exceeds available quantity")
    total_cost = state.average_cost * state.quantity
    positions[instrument_id] = _PositionState(
        quantity=new_quantity,
        available_quantity=new_available_quantity,
        average_cost=_price(total_cost / new_quantity),
        realized_pnl=state.realized_pnl,
        total_fees=state.total_fees,
    )
