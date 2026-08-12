"""Application adapter from the backtest risk port to ContinuousRiskGate."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

import orjson
from ditto_backtest.risk_runtime import (
    BacktestRiskContext,
    BacktestRiskDecision,
    DailyRiskOutcome,
)
from ditto_execution.orders.model import Order
from ditto_portfolio.accounting import AccountView, FillEvent
from ditto_risk.continuous_gate import (
    ContinuousRiskGate,
    DailyRiskInput,
    FillRiskContext,
    RiskDecisionKind,
    RiskGateContext,
    RiskStateSnapshot,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.risk.fingerprint import position_fingerprint

__all__ = ["ContinuousRiskBacktestAdapter", "position_fingerprint"]

_PAIR_SIZE = 2


class ContinuousRiskBacktestAdapter:
    """Bind one pure gate to one backtest account/sleeve identity."""

    def __init__(
        self,
        *,
        gate: ContinuousRiskGate,
        account_id: str,
        sleeve_id: str,
    ) -> None:
        self._gate = gate
        self._account_id = account_id
        self._sleeve_id = sleeve_id

    def daily_scan(self, context: BacktestRiskContext) -> DailyRiskOutcome:
        """Run the daily gate against the authoritative portfolio snapshot."""
        report = self._gate.daily_scan(
            DailyRiskInput(
                context=self._gate_context(context),
                nav=context.account_view.nav,
            )
        )
        return DailyRiskOutcome(
            readiness=report.readiness,
            block_reasons=report.block_reasons,
            evidence=asdict(report),
        )

    def pre_trade(
        self,
        order: Order,
        context: BacktestRiskContext,
    ) -> BacktestRiskDecision:
        """Translate the pure gate result without weakening rejection semantics."""
        result = self._gate.pre_trade(order, self._gate_context(context))
        adjusted = result.adjusted_order
        adjusted_order = adjusted if isinstance(adjusted, Order) else None
        return BacktestRiskDecision(
            allow=result.kind is RiskDecisionKind.ALLOW and adjusted_order is not None,
            adjusted_order=adjusted_order,
            reason_code=result.reason_code,
            reason=result.reason,
            triggered_checks=result.triggered_checks,
        )

    def post_fill(
        self,
        fill: FillEvent,
        context: BacktestRiskContext,
        event_id: str,
    ) -> None:
        """Apply the next fill with a monotonic sequence owned by the gate."""
        snapshot = self._gate.snapshot_state()
        sequence = (
            snapshot.processed_event_ids.index(event_id) + 1
            if event_id in snapshot.processed_event_ids
            else snapshot.event_sequence + 1
        )
        self._gate.post_fill(
            fill,
            FillRiskContext(
                account_id=self._account_id,
                sleeve_id=self._sleeve_id,
                trade_date=context.trade_date,
                account_view=context.account_view,
                position_fingerprint=position_fingerprint(context.account_view),
                event_sequence=sequence,
            ),
            event_id,
        )

    def snapshot_state_json(self) -> str:
        """Serialize the integrity-protected risk snapshot canonically."""
        return orjson.dumps(
            asdict(self._gate.snapshot_state()),
            option=orjson.OPT_SORT_KEYS,
        ).decode()

    def restore_state_json(
        self,
        payload_json: str,
        account_view: AccountView,
    ) -> None:
        """Decode typed state and validate it against the authoritative ledger."""
        payload = cast(dict[str, object], orjson.loads(payload_json))
        snapshot = RiskStateSnapshot(
            schema_version=_int_field(payload, "schema_version"),
            account_id=_str_field(payload, "account_id"),
            sleeve_id=_str_field(payload, "sleeve_id"),
            trade_date=_optional_str_field(payload, "trade_date"),
            peak_nav=_float_field(payload, "peak_nav"),
            current_drawdown=_float_field(payload, "current_drawdown"),
            daily_turnover_notional=_float_field(
                payload,
                "daily_turnover_notional",
            ),
            locked=_bool_field(payload, "locked"),
            lock_reasons=_str_tuple_field(payload, "lock_reasons"),
            event_sequence=_int_field(payload, "event_sequence"),
            processed_event_ids=_str_tuple_field(payload, "processed_event_ids"),
            processed_event_digests=_str_pair_tuple_field(
                payload,
                "processed_event_digests",
            ),
            position_fingerprint=_optional_str_field(
                payload,
                "position_fingerprint",
            ),
            integrity_hash=_str_field(payload, "integrity_hash"),
        )
        self._gate.restore_state(
            snapshot,
            expected_position_fingerprint=position_fingerprint(account_view),
        )

    def _gate_context(self, context: BacktestRiskContext) -> RiskGateContext:
        return RiskGateContext(
            account_id=self._account_id,
            sleeve_id=self._sleeve_id,
            trade_date=context.trade_date,
            account_view=context.account_view,
            position_fingerprint=position_fingerprint(context.account_view),
            pre_trade_context=context.pre_trade_context,
        )


def _str_field(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AppProcessError(
            f"risk checkpoint field {name!r} must be a non-empty string"
        )
    return value


def _optional_str_field(payload: dict[str, object], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise AppProcessError(f"risk checkpoint field {name!r} must be string or null")
    return value


def _int_field(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if type(value) is not int:
        raise AppProcessError(f"risk checkpoint field {name!r} must be an integer")
    return value


def _float_field(payload: dict[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AppProcessError(f"risk checkpoint field {name!r} must be numeric")
    return float(value)


def _bool_field(payload: dict[str, object], name: str) -> bool:
    value = payload.get(name)
    if type(value) is not bool:
        raise AppProcessError(f"risk checkpoint field {name!r} must be boolean")
    return value


def _str_tuple_field(payload: dict[str, object], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise AppProcessError(f"risk checkpoint field {name!r} must be a string list")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise AppProcessError(f"risk checkpoint field {name!r} must be a string list")
    return tuple(cast(list[str], items))


def _str_pair_tuple_field(
    payload: dict[str, object],
    name: str,
) -> tuple[tuple[str, str], ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise AppProcessError(f"risk checkpoint field {name!r} must be a pair list")
    items = cast(list[object], value)
    result: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, list):
            raise AppProcessError(f"risk checkpoint field {name!r} must be a pair list")
        parts = cast(list[object], item)
        if len(parts) != _PAIR_SIZE or not all(isinstance(part, str) for part in parts):
            raise AppProcessError(f"risk checkpoint field {name!r} must be a pair list")
        pair = cast(list[str], parts)
        result.append((pair[0], pair[1]))
    return tuple(result)
