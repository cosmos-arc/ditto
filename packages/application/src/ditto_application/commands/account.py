"""Account baseline command contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from math import isfinite

import orjson
from ditto_execution.audit.models import AccountBaselineAuditPayload
from ditto_execution.contracts import AccountDataPort, PositionDataPort
from ditto_execution.models import AccountSnapshotRecord, PositionRecord

from ditto_application.account_baseline_integrity import (
    resolve_complete_baseline_positions,
)
from ditto_application.exceptions import AppCommandError

__all__ = [
    "AccountBaselineResult",
    "ImportAccountBaselineCommand",
    "ImportAccountBaselineHandler",
    "PositionBaselineInput",
]


@dataclass(frozen=True)
class PositionBaselineInput:
    """账户基线中的单只标的持仓输入。"""

    instrument_id: int
    quantity: int
    available_quantity: int
    average_cost: float
    market_value: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0


@dataclass(frozen=True)
class ImportAccountBaselineCommand:
    """导入账户与持仓基线命令。"""

    account_id: str
    strategy_id: str
    snapshot_date: str
    cash_available: float
    cash_settled: float
    cash_frozen: float
    total_value: float
    nav: float
    positions: tuple[PositionBaselineInput, ...] = ()
    replace_confirmed: bool = False


@dataclass(frozen=True)
class AccountBaselineResult:
    """账户基线导入结果。"""

    snapshot_id: str
    sleeve_id: str
    status: str


class ImportAccountBaselineHandler:
    """校验并幂等保存账户与持仓基线。"""

    def __init__(
        self,
        *,
        account_port: AccountDataPort,
        position_port: PositionDataPort,
    ) -> None:
        self._account_port = account_port
        self._position_port = position_port

    def handle(self, command: ImportAccountBaselineCommand) -> AccountBaselineResult:
        """执行基线导入；差异覆盖必须显式确认。"""
        _validate(command)
        sleeve_id = f"manual-{command.account_id}-{command.strategy_id}"
        exposure = sum(position.market_value for position in command.positions)
        payload = _identity_payload(command, sleeve_id=sleeve_id, exposure=exposure)
        snapshot_id = f"baseline-{sha256(orjson.dumps(payload)).hexdigest()[:24]}"
        created_at = datetime.now(UTC).isoformat()
        account = AccountSnapshotRecord(
            snapshot_id=snapshot_id,
            run_id=sleeve_id,
            strategy_id=command.strategy_id,
            account_id=command.account_id,
            snapshot_date=command.snapshot_date,
            cash_available=command.cash_available,
            cash_settled=command.cash_settled,
            cash_frozen=command.cash_frozen,
            total_value=command.total_value,
            nav=command.nav,
            exposure=exposure,
            created_at=created_at,
        )
        existing = self._account_port.list_account_snapshots(
            sleeve_id,
            strategy_id=command.strategy_id,
            account_id=command.account_id,
            snapshot_date=command.snapshot_date,
        )
        current: AccountSnapshotRecord | None = None
        if existing:
            current = max(
                existing,
                key=lambda item: (item.created_at, item.snapshot_id),
            )
            if current.snapshot_id == snapshot_id:
                self._require_complete_positions(
                    current,
                    error_message=(
                        "existing baseline positions are incomplete or inconsistent"
                    ),
                )
                return AccountBaselineResult(snapshot_id, sleeve_id, "unchanged")
            if not command.replace_confirmed:
                raise AppCommandError(
                    "Account baseline differs; set replace_confirmed=true"
                )
            status = "replaced"
        else:
            status = "created"

        old_positions = self._old_positions(current)

        positions = tuple(
            PositionRecord(
                snapshot_id=f"{snapshot_id}-{position.instrument_id}",
                run_id=sleeve_id,
                strategy_id=command.strategy_id,
                snapshot_date=command.snapshot_date,
                instrument_id=position.instrument_id,
                quantity=position.quantity,
                available_quantity=position.available_quantity,
                average_cost=position.average_cost,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.realized_pnl,
                total_fees=position.total_fees,
                created_at=created_at,
            )
            for position in command.positions
        )
        self._account_port.save_account_baseline(
            account=account,
            positions=positions,
            audit_payload=AccountBaselineAuditPayload(
                trade_date=command.snapshot_date,
                operation="correction" if current is not None else "import",
                account_id=command.account_id,
                strategy_id=command.strategy_id,
                sleeve_id=sleeve_id,
                old_snapshot_id=current.snapshot_id if current is not None else None,
                new_snapshot_id=snapshot_id,
                old_baseline=(
                    _old_baseline_payload(current, old_positions)
                    if current is not None
                    else None
                ),
                new_baseline=payload,
            ),
        )
        return AccountBaselineResult(snapshot_id, sleeve_id, status)

    def _old_positions(
        self, current: AccountSnapshotRecord | None
    ) -> tuple[PositionRecord, ...]:
        """Read the positions belonging to the superseded aggregate."""
        if current is None:
            return ()
        return self._require_complete_positions(
            current,
            error_message=(
                "superseded baseline positions are incomplete or inconsistent for audit"
            ),
        )

    def _require_complete_positions(
        self,
        current: AccountSnapshotRecord,
        *,
        error_message: str,
    ) -> tuple[PositionRecord, ...]:
        """Load one exact persisted aggregate and fail closed if it is incomplete."""
        candidates = self._position_port.list_positions(
            current.strategy_id,
            snapshot_date=current.snapshot_date,
            run_id=current.run_id,
        )
        positions = resolve_complete_baseline_positions(
            current,
            candidates,
        )
        if positions is None:
            raise AppCommandError(error_message)
        return positions


def _identity_payload(
    command: ImportAccountBaselineCommand,
    *,
    sleeve_id: str,
    exposure: float,
) -> dict[str, object]:
    return {
        "account_id": command.account_id,
        "strategy_id": command.strategy_id,
        "sleeve_id": sleeve_id,
        "snapshot_date": command.snapshot_date,
        "cash_available": command.cash_available,
        "cash_settled": command.cash_settled,
        "cash_frozen": command.cash_frozen,
        "total_value": command.total_value,
        "nav": command.nav,
        "exposure": exposure,
        "positions": [
            {
                "instrument_id": position.instrument_id,
                "quantity": position.quantity,
                "available_quantity": position.available_quantity,
                "average_cost": position.average_cost,
                "market_value": position.market_value,
                "unrealized_pnl": position.unrealized_pnl,
                "realized_pnl": position.realized_pnl,
                "total_fees": position.total_fees,
            }
            for position in sorted(
                command.positions, key=lambda item: item.instrument_id
            )
        ],
    }


def _old_baseline_payload(
    account: AccountSnapshotRecord,
    positions: tuple[PositionRecord, ...],
) -> dict[str, object]:
    """Serialize the complete superseded account baseline for typed audit."""
    payload = asdict(account)
    payload["positions"] = [
        {
            "instrument_id": position.instrument_id,
            "quantity": position.quantity,
            "available_quantity": position.available_quantity,
            "average_cost": position.average_cost,
            "market_value": position.market_value,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "total_fees": position.total_fees,
        }
        for position in sorted(positions, key=lambda item: item.instrument_id)
    ]
    return payload


def _validate(command: ImportAccountBaselineCommand) -> None:
    _validate_snapshot_date(command.snapshot_date)
    _validate_account_amounts(command)
    _validate_positions(command.positions)
    exposure = sum(position.market_value for position in command.positions)
    expected_total = command.cash_available + command.cash_frozen + exposure
    tolerance = max(1.0, command.total_value * 0.01)
    if abs(command.total_value - expected_total) > tolerance:
        raise AppCommandError("total_value is inconsistent with cash and positions")


def _validate_snapshot_date(snapshot_date: str) -> None:
    try:
        date.fromisoformat(snapshot_date)
    except ValueError as exc:
        raise AppCommandError("snapshot_date must be a valid YYYY-MM-DD date") from exc


def _validate_account_amounts(command: ImportAccountBaselineCommand) -> None:
    for name in (
        "cash_available",
        "cash_settled",
        "cash_frozen",
        "total_value",
        "nav",
    ):
        value = getattr(command, name)
        if not isfinite(value):
            raise AppCommandError(f"{name} must be finite")
        if value < 0:
            raise AppCommandError(f"{name} must be non-negative")


def _validate_positions(positions: tuple[PositionBaselineInput, ...]) -> None:
    instrument_ids: set[int] = set()
    for position in positions:
        if position.instrument_id in instrument_ids:
            raise AppCommandError(f"duplicate instrument_id: {position.instrument_id}")
        instrument_ids.add(position.instrument_id)
        _validate_position(position)


def _validate_position(position: PositionBaselineInput) -> None:
    for name in (
        "quantity",
        "available_quantity",
        "average_cost",
        "market_value",
        "unrealized_pnl",
        "realized_pnl",
        "total_fees",
    ):
        if not isfinite(getattr(position, name)):
            raise AppCommandError(f"{name} must be finite")
    if position.quantity < 0:
        raise AppCommandError("quantity must be non-negative")
    if not 0 <= position.available_quantity <= position.quantity:
        raise AppCommandError("available_quantity must be within quantity")
    if position.average_cost < 0 or position.market_value < 0:
        raise AppCommandError("position values must be non-negative")
    if position.total_fees < 0:
        raise AppCommandError("total_fees must be non-negative")
