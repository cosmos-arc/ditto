"""Typed, JSON-safe execution-audit history for exact checkpoint resume."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import cast

import orjson
from ditto_execution.trade_builder import TradeRecord
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting import (
    AccountView,
    CashBook,
    FillEvent,
    Position,
)
from ditto_risk.post_trade import RiskActionType, RiskSeverity

from ditto_backtest._account_checkpoint import BacktestAccountStateSnapshot
from ditto_backtest._checkpoint_codec import (
    finite_float,
    optional_finite_float,
    payload_float,
    payload_int,
    payload_mapping,
    payload_optional_float,
    payload_optional_int,
    payload_optional_str,
    payload_sequence,
    payload_str,
)
from ditto_backtest.audit.records import (
    PreTradeDecisionRecord,
    RiskScanRecord,
)

__all__ = ["ExecutionAuditStateSnapshot"]


@dataclass(frozen=True)
class ExecutionAuditStateSnapshot:
    """All append-only audit inputs needed to rebuild a full-run report."""

    fills: tuple[FillEvent, ...] = ()
    daily_snapshots: tuple[tuple[str, BacktestAccountStateSnapshot], ...] = ()
    closed_trades: tuple[TradeRecord, ...] = ()
    risk_log: tuple[RiskScanRecord, ...] = ()
    pre_trade_log: tuple[PreTradeDecisionRecord, ...] = ()

    @classmethod
    def capture(
        cls,
        *,
        fills: tuple[FillEvent, ...],
        daily_snapshots: tuple[tuple[str, AccountView], ...],
        closed_trades: tuple[TradeRecord, ...],
        risk_log: tuple[RiskScanRecord, ...],
        pre_trade_log: tuple[PreTradeDecisionRecord, ...],
    ) -> ExecutionAuditStateSnapshot:
        """Copy one collector's append-only history into immutable DTOs."""
        return cls(
            fills=fills,
            daily_snapshots=tuple(
                (trade_date, BacktestAccountStateSnapshot.from_account_view(view))
                for trade_date, view in daily_snapshots
            ),
            closed_trades=closed_trades,
            risk_log=risk_log,
            pre_trade_log=pre_trade_log,
        )

    def to_daily_snapshots(self) -> tuple[tuple[str, AccountView], ...]:
        """Rebuild immutable AccountView history in its original order."""
        return tuple(
            (trade_date, _account_view_from_snapshot(snapshot))
            for trade_date, snapshot in self.daily_snapshots
        )

    def to_payload(self) -> dict[str, object]:
        """Return a canonical JSON-safe payload without reordering history."""
        return {
            "closed_trades": [_trade_to_payload(item) for item in self.closed_trades],
            "daily_snapshots": [
                {
                    "account": account.to_payload(),
                    "trade_date": trade_date,
                }
                for trade_date, account in self.daily_snapshots
            ],
            "fills": [_fill_to_payload(item) for item in self.fills],
            "pre_trade_log": [
                _pre_trade_to_payload(item) for item in self.pre_trade_log
            ],
            "risk_log": [_risk_to_payload(item) for item in self.risk_log],
        }

    def to_json(self) -> str:
        """Serialize audit history with deterministic object-key ordering."""
        return orjson.dumps(self.to_payload(), option=orjson.OPT_SORT_KEYS).decode()

    @classmethod
    def from_payload(cls, payload: object) -> ExecutionAuditStateSnapshot:
        """Strictly decode every V2 audit-history collection."""
        data = payload_mapping(payload)
        for key in (
            "closed_trades",
            "daily_snapshots",
            "fills",
            "pre_trade_log",
            "risk_log",
        ):
            if key not in data:
                msg = f"checkpoint audit field {key!r} is required"
                raise ValueError(msg)
        return cls(
            fills=tuple(
                _fill_from_payload(item) for item in payload_sequence(data, "fills")
            ),
            daily_snapshots=tuple(
                _daily_snapshot_from_payload(item)
                for item in payload_sequence(data, "daily_snapshots")
            ),
            closed_trades=tuple(
                _trade_from_payload(item)
                for item in payload_sequence(data, "closed_trades")
            ),
            risk_log=tuple(
                _risk_from_payload(item) for item in payload_sequence(data, "risk_log")
            ),
            pre_trade_log=tuple(
                _pre_trade_from_payload(item)
                for item in payload_sequence(data, "pre_trade_log")
            ),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> ExecutionAuditStateSnapshot:
        """Deserialize canonical audit-history JSON."""
        return cls.from_payload(cast(object, orjson.loads(payload_json)))

    @classmethod
    def from_canonical_json(cls, payload_json: str) -> ExecutionAuditStateSnapshot:
        """Decode only the one canonical JSON representation used for hashing."""
        snapshot = cls.from_json(payload_json)
        if snapshot.to_json() != payload_json:
            raise ValueError("checkpoint audit history JSON is not canonical")
        return snapshot


def _account_view_from_snapshot(snapshot: BacktestAccountStateSnapshot) -> AccountView:
    positions = {
        item.instrument_id: Position(
            instrument_id=item.instrument_id,
            quantity=item.quantity,
            available_quantity=item.available_quantity,
            average_cost=item.average_cost,
            market_value=item.market_value,
            unrealized_pnl=item.unrealized_pnl,
            realized_pnl=item.realized_pnl,
            total_fees=item.total_fees,
        )
        for item in snapshot.positions
    }
    return AccountView(
        positions=MappingProxyType(positions),
        cash=CashBook(
            available=snapshot.cash_available,
            settled=snapshot.cash_settled,
            frozen=snapshot.cash_frozen,
        ),
        total_value=snapshot.total_value,
        nav=snapshot.nav,
        exposure=snapshot.exposure,
    )


def _fill_to_payload(fill: FillEvent) -> dict[str, object]:
    return {
        "correlation_id": fill.correlation_id,
        "cumulative_quantity": fill.cumulative_quantity,
        "direction": fill.direction.value,
        "event_time": fill.event_time.isoformat(),
        "fee": finite_float(fill.fee, "fee"),
        "fill_id": fill.fill_id,
        "fill_price": finite_float(fill.fill_price, "fill_price"),
        "filled_quantity": fill.filled_quantity,
        "instrument_id": int(fill.instrument_id),
        "leaves_quantity": fill.leaves_quantity,
        "order_id": fill.order_id,
        "slippage": finite_float(fill.slippage, "slippage"),
    }


def _fill_from_payload(payload: object) -> FillEvent:
    data = payload_mapping(payload)
    _require_keys(
        data,
        (
            "correlation_id",
            "cumulative_quantity",
            "direction",
            "event_time",
            "fee",
            "fill_id",
            "fill_price",
            "filled_quantity",
            "instrument_id",
            "leaves_quantity",
            "order_id",
            "slippage",
        ),
    )
    return FillEvent(
        fill_id=payload_str(data, "fill_id"),
        order_id=payload_str(data, "order_id"),
        instrument_id=InstrumentId(payload_int(data, "instrument_id")),
        direction=OrderSide(payload_str(data, "direction")),
        filled_quantity=payload_int(data, "filled_quantity"),
        fill_price=payload_float(data, "fill_price"),
        fee=payload_float(data, "fee"),
        slippage=payload_float(data, "slippage"),
        event_time=_payload_datetime(data, "event_time"),
        cumulative_quantity=payload_int(data, "cumulative_quantity"),
        leaves_quantity=payload_int(data, "leaves_quantity"),
        correlation_id=payload_optional_str(data, "correlation_id"),
    )


def _trade_to_payload(trade: TradeRecord) -> dict[str, object]:
    return {
        "direction": trade.direction.value,
        "entry_date": trade.entry_date,
        "entry_order_ids": list(trade.entry_order_ids),
        "entry_price": finite_float(trade.entry_price, "entry_price"),
        "exit_date": trade.exit_date,
        "exit_order_ids": list(trade.exit_order_ids),
        "exit_price": optional_finite_float(trade.exit_price, "exit_price"),
        "fees": finite_float(trade.fees, "fees"),
        "gross_pnl": optional_finite_float(trade.gross_pnl, "gross_pnl"),
        "holding_days": trade.holding_days,
        "instrument_id": int(trade.instrument_id),
        "net_pnl": optional_finite_float(trade.net_pnl, "net_pnl"),
        "quantity": trade.quantity,
        "return_pct": optional_finite_float(trade.return_pct, "return_pct"),
        "trade_id": trade.trade_id,
    }


def _trade_from_payload(payload: object) -> TradeRecord:
    data = payload_mapping(payload)
    _require_keys(
        data,
        (
            "direction",
            "entry_date",
            "entry_order_ids",
            "entry_price",
            "exit_date",
            "exit_order_ids",
            "exit_price",
            "fees",
            "gross_pnl",
            "holding_days",
            "instrument_id",
            "net_pnl",
            "quantity",
            "return_pct",
            "trade_id",
        ),
    )
    return TradeRecord(
        trade_id=payload_str(data, "trade_id"),
        instrument_id=InstrumentId(payload_int(data, "instrument_id")),
        direction=OrderSide(payload_str(data, "direction")),
        entry_date=_payload_date_str(data, "entry_date"),
        exit_date=_payload_optional_date_str(data, "exit_date"),
        entry_price=payload_float(data, "entry_price"),
        exit_price=payload_optional_float(data, "exit_price"),
        quantity=payload_int(data, "quantity"),
        gross_pnl=payload_optional_float(data, "gross_pnl"),
        fees=payload_float(data, "fees"),
        net_pnl=payload_optional_float(data, "net_pnl"),
        holding_days=_optional_int(data, "holding_days"),
        return_pct=payload_optional_float(data, "return_pct"),
        entry_order_ids=_string_tuple(data, "entry_order_ids"),
        exit_order_ids=_string_tuple(data, "exit_order_ids"),
    )


def _risk_to_payload(record: RiskScanRecord) -> dict[str, object]:
    return {
        "action_taken": RiskActionType(record.action_taken).value,
        "current_value": finite_float(record.current_value, "current_value"),
        "detail": record.detail,
        "instrument_id": (
            None if record.instrument_id is None else int(record.instrument_id)
        ),
        "rule_id": record.rule_id,
        "scope": RiskScope(record.scope).value,
        "severity": RiskSeverity(record.severity).value,
        "threshold": finite_float(record.threshold, "threshold"),
        "trade_date": record.trade_date,
    }


def _risk_from_payload(payload: object) -> RiskScanRecord:
    data = payload_mapping(payload)
    _require_keys(
        data,
        (
            "action_taken",
            "current_value",
            "detail",
            "instrument_id",
            "rule_id",
            "scope",
            "severity",
            "threshold",
            "trade_date",
        ),
    )
    instrument_id = data.get("instrument_id")
    if instrument_id is not None and type(instrument_id) is not int:
        raise ValueError("checkpoint risk instrument_id must be an integer or null")
    return RiskScanRecord(
        trade_date=_payload_date_str(data, "trade_date"),
        rule_id=payload_str(data, "rule_id"),
        instrument_id=(None if instrument_id is None else InstrumentId(instrument_id)),
        scope=RiskScope(payload_str(data, "scope")),
        severity=RiskSeverity(payload_str(data, "severity")),
        action_taken=RiskActionType(payload_str(data, "action_taken")),
        detail=payload_str(data, "detail"),
        current_value=payload_float(data, "current_value"),
        threshold=payload_float(data, "threshold"),
    )


def _pre_trade_to_payload(record: PreTradeDecisionRecord) -> dict[str, object]:
    return {
        "check_sequence": list(record.check_sequence),
        "decision": record.decision,
        "direction": record.direction,
        "final_quantity": record.final_quantity,
        "instrument_id": int(record.instrument_id),
        "order_id": record.order_id,
        "original_quantity": record.original_quantity,
        "reason": record.reason,
        "trade_date": record.trade_date,
    }


def _pre_trade_from_payload(payload: object) -> PreTradeDecisionRecord:
    data = payload_mapping(payload)
    _require_keys(
        data,
        (
            "check_sequence",
            "decision",
            "direction",
            "final_quantity",
            "instrument_id",
            "order_id",
            "original_quantity",
            "reason",
            "trade_date",
        ),
    )
    return PreTradeDecisionRecord(
        trade_date=_payload_date_str(data, "trade_date"),
        order_id=payload_str(data, "order_id"),
        instrument_id=InstrumentId(payload_int(data, "instrument_id")),
        direction=payload_str(data, "direction"),
        original_quantity=payload_int(data, "original_quantity"),
        final_quantity=payload_int(data, "final_quantity"),
        decision=payload_str(data, "decision"),
        reason=payload_optional_str(data, "reason"),
        check_sequence=_string_tuple(data, "check_sequence"),
    )


def _daily_snapshot_from_payload(
    payload: object,
) -> tuple[str, BacktestAccountStateSnapshot]:
    data = payload_mapping(payload)
    _require_keys(data, ("account", "trade_date"))
    account = payload_mapping(data["account"])
    _require_keys(
        account,
        (
            "cash_available",
            "cash_frozen",
            "cash_settled",
            "exposure",
            "nav",
            "positions",
            "total_value",
        ),
    )
    for position in payload_sequence(account, "positions"):
        _require_keys(
            position,
            (
                "available_quantity",
                "average_cost",
                "instrument_id",
                "market_value",
                "quantity",
                "realized_pnl",
                "total_fees",
                "unrealized_pnl",
            ),
        )
    return (
        _payload_date_str(data, "trade_date"),
        BacktestAccountStateSnapshot.from_payload(account),
    )


def _payload_datetime(data: object, key: str) -> datetime:
    try:
        return datetime.fromisoformat(payload_str(payload_mapping(data), key))
    except ValueError:
        raise ValueError(f"checkpoint field {key!r} must be ISO datetime") from None


def _payload_date_str(data: object, key: str) -> str:
    value = payload_str(payload_mapping(data), key)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"checkpoint field {key!r} must be ISO date") from None
    return value


def _payload_optional_date_str(data: object, key: str) -> str | None:
    value = payload_optional_str(payload_mapping(data), key)
    if value is None:
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"checkpoint field {key!r} must be ISO date or null") from None
    return value


def _optional_int(data: object, key: str) -> int | None:
    mapping = payload_mapping(data)
    if mapping.get(key) is None:
        return None
    return payload_optional_int(mapping, key)


def _string_tuple(data: object, key: str) -> tuple[str, ...]:
    values = payload_sequence(payload_mapping(data), key)
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"checkpoint field {key!r} must contain only strings")
    return cast(tuple[str, ...], values)


def _require_keys(payload: object, keys: tuple[str, ...]) -> None:
    data = payload_mapping(payload)
    missing = tuple(key for key in keys if key not in data)
    if missing:
        raise ValueError(f"checkpoint audit record is missing fields: {missing!r}")
