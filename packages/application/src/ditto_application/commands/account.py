"""Account baseline command contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256

import orjson
from ditto_execution.audit.models import AccountBaselineAuditPayload
from ditto_execution.contracts import AccountDataPort
from ditto_execution.models import AccountSnapshotRecord, PositionRecord

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

    def __init__(self, *, account_port: AccountDataPort) -> None:
        self._account_port = account_port

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
            current = existing[-1]
            if current.snapshot_id == snapshot_id:
                return AccountBaselineResult(snapshot_id, sleeve_id, "unchanged")
            if not command.replace_confirmed:
                raise AppCommandError(
                    "Account baseline differs; set replace_confirmed=true"
                )
            status = "replaced"
        else:
            status = "created"

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
                old_baseline=asdict(current) if current is not None else None,
                new_baseline=payload,
            ),
        )
        return AccountBaselineResult(snapshot_id, sleeve_id, status)


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


def _validate(command: ImportAccountBaselineCommand) -> None:
    for name in (
        "cash_available",
        "cash_settled",
        "cash_frozen",
        "total_value",
        "nav",
    ):
        if getattr(command, name) < 0:
            raise AppCommandError(f"{name} must be non-negative")
    instrument_ids: set[int] = set()
    for position in command.positions:
        if position.instrument_id in instrument_ids:
            raise AppCommandError(f"duplicate instrument_id: {position.instrument_id}")
        instrument_ids.add(position.instrument_id)
        if position.quantity < 0:
            raise AppCommandError("quantity must be non-negative")
        if not 0 <= position.available_quantity <= position.quantity:
            raise AppCommandError("available_quantity must be within quantity")
        if position.average_cost < 0 or position.market_value < 0:
            raise AppCommandError("position values must be non-negative")
    exposure = sum(position.market_value for position in command.positions)
    expected_total = command.cash_available + command.cash_frozen + exposure
    tolerance = max(1.0, command.total_value * 0.01)
    if abs(command.total_value - expected_total) > tolerance:
        raise AppCommandError("total_value is inconsistent with cash and positions")
