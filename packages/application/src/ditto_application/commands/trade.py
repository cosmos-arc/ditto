"""成交录入命令 DTO + Handler — 录入人工成交、更新交易意图状态."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite

from ditto_execution.contracts import FillDataPort, IntentDataPort, PositionDataPort
from ditto_execution.errors import (
    FillConflictError,
    FillNotFoundError,
    FillProcessingError,
)
from ditto_execution.models import FillAdjustmentRecord, FillRecord, SignalRecord

from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
)
from ditto_application.execution_dto import (
    FillAdjustment,
    ManualExecutionFill,
    fill_to_record,
    record_to_adjustment,
    record_to_fill,
    record_to_snapshot,
    snapshot_to_record,
)
from ditto_application.opening_baseline import OpeningBaselinePort
from ditto_application.processes.execution.manual_tracker import ManualTracker

__all__ = [
    "ProjectedFillAppendAdapter",
    "ProjectedFillCorrectionAdapter",
    "RecordFillCommand",
    "RecordFillHandler",
    "ReplaceFillCommand",
    "ReplaceFillHandler",
    "UpdateIntentStatusCommand",
    "UpdateIntentStatusHandler",
    "VoidFillCommand",
    "VoidFillHandler",
]

_VALID_INTENT_STATUSES = {
    "pending",
    "filled",
    "partially_filled",
    "cancelled",
    "expired",
    "superseded",
}

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {
        "filled",
        "partially_filled",
        "cancelled",
        "expired",
        "superseded",
    },
    "partially_filled": {"filled", "partially_filled", "cancelled", "expired"},
    "filled": set(),  # terminal
    "cancelled": set(),  # terminal
    "expired": set(),  # terminal
    "superseded": set(),  # terminal
}


@dataclass(frozen=True)
class RecordFillCommand:
    """录入人工成交命令."""

    fill_id: str
    intent_id: str
    strategy_id: str
    trade_date: str
    instrument_id: int
    direction: str
    quantity: int
    fill_price: float
    fee: float = 0.0
    slippage: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class VoidFillCommand:
    """Append a void event for one immutable fill."""

    adjustment_id: str
    fill_id: str
    reason: str


@dataclass(frozen=True)
class ReplaceFillCommand:
    """Append a corrected replacement fill and link it to the source fill."""

    adjustment_id: str
    fill_id: str
    replacement_fill_id: str
    trade_date: str
    quantity: int
    fill_price: float
    reason: str
    fee: float = 0.0
    slippage: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class UpdateIntentStatusCommand:
    """更新交易意图状态命令."""

    intent_id: str
    status: str


class ProjectedFillAppendAdapter:
    """Append one immutable fill and update its derived projections atomically."""

    def __init__(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> None:
        self._intent = intent_port
        self._fill = fill_port
        self._position = position_port
        self._tracker = manual_tracker
        self._opening_baseline = opening_baseline_resolver

    def append_projected_fill(self, record: FillRecord) -> bool:
        """Append a fill; an exact replay performs no projection side effects."""
        intent = self._intent.get_intent(record.intent_id)
        _validate_fill_identity(intent, record)
        if intent is None:  # pragma: no cover - narrowed by validator
            raise AppNotFoundError(f"Intent not found: {record.intent_id}")
        try:
            with self._fill.ledger_transaction():
                created = self._fill.save_fill(record)
                if created is False:
                    return False

                locked_intent = self._intent.get_intent(record.intent_id)
                _validate_fill_identity(locked_intent, record)
                if locked_intent is None:  # pragma: no cover - validator narrows
                    raise AppNotFoundError(f"Intent not found: {record.intent_id}")
                effective = self._fill.list_effective_fills(
                    locked_intent.strategy_id,
                    intent_id=locked_intent.intent_id,
                )
                new_status = _effective_intent_status(
                    locked_intent.quantity,
                    effective,
                )
                updated = self._intent.update_intent_status(
                    locked_intent.intent_id,
                    new_status,
                    expected_current=(locked_intent.status,),
                )
                if not updated:
                    msg = f"Concurrent fill update conflict: {locked_intent.intent_id}"
                    raise AppConflictError(msg)
                _rebuild_manual_positions(
                    fill_port=self._fill,
                    position_port=self._position,
                    tracker=self._tracker,
                    intent=locked_intent,
                    changed_date=record.trade_date,
                    opening_baseline_resolver=self._opening_baseline,
                )
        except FillConflictError as exc:
            raise AppConflictError(str(exc)) from exc
        except FillNotFoundError as exc:
            raise AppNotFoundError(str(exc)) from exc
        except FillProcessingError as exc:
            raise AppCommandError(str(exc)) from exc
        return True


class RecordFillHandler:
    """录入人工成交 — Command Handler（跨聚合编排：Intent + Fill + Position）."""

    def __init__(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
        projected_fill_adapter: ProjectedFillAppendAdapter | None = None,
    ) -> None:
        self._intent = intent_port
        self._fill = fill_port
        self._position = position_port
        self._tracker = manual_tracker
        self._projected_fill = projected_fill_adapter or ProjectedFillAppendAdapter(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=manual_tracker,
            opening_baseline_resolver=opening_baseline_resolver,
        )

    def handle(self, command: RecordFillCommand) -> ManualExecutionFill:
        """
        处理成交录入命令.

        0. 幂等性: 只按 fill_id 检查请求 payload
        1. 验证 intent_id 有效 + 身份校验
        2. 构建 ManualExecutionFill DTO
        3. 映射为 Record 并持久化
        4. 更新 intent 状态（支持部分成交）
        5. 触发 ManualTracker 重新聚合 -> 更新持仓
        """
        # 0. fill_id 是唯一幂等键；intent/date 可以有任意多笔部分成交。
        existing_fill_record = self._fill.get_fill(command.fill_id)
        if existing_fill_record is not None:
            if not self._same_fill_request(existing_fill_record, command):
                msg = f"Fill ID conflict: {command.fill_id}"
                raise AppConflictError(msg)
            return record_to_fill(existing_fill_record)

        # 1. Validate
        intent_record = self._intent.get_intent(command.intent_id)
        self._validate_intent_match(intent_record, command)
        # _validate_intent_match raises when None; narrow for type checker
        if intent_record is None:
            raise AppNotFoundError(f"Intent not found: {command.intent_id}")

        # 2. Build DTO
        fill = self._build_fill_dto(command, self._tracker)

        # 3-5. Persist the immutable fill and derived projections atomically.
        record = fill_to_record(fill)
        created = self._projected_fill.append_projected_fill(record)
        if not created:
            canonical = self._fill.get_fill(command.fill_id)
            if canonical is None:
                raise AppNotFoundError(
                    f"Fill not found after replay: {command.fill_id}"
                )
            return record_to_fill(canonical)
        return fill

    @staticmethod
    def _same_fill_request(
        existing: FillRecord,
        command: RecordFillCommand,
    ) -> bool:
        """Compare persisted request facts without generated timestamps/settlement."""
        return (
            existing.fill_id == command.fill_id
            and existing.intent_id == command.intent_id
            and existing.strategy_id == command.strategy_id
            and existing.trade_date == command.trade_date
            and existing.instrument_id == command.instrument_id
            and existing.direction == command.direction
            and existing.quantity == command.quantity
            and existing.fill_price == command.fill_price
            and existing.fee == command.fee
            and existing.slippage == command.slippage
            and existing.notes == command.notes
        )

    @staticmethod
    def _validate_intent_match(
        intent_record: SignalRecord | None,
        command: RecordFillCommand,
    ) -> None:
        """验证 intent 存在且身份信息匹配."""
        if intent_record is None:
            msg = f"Intent not found: {command.intent_id}"
            raise AppNotFoundError(msg)

        if intent_record.strategy_id != command.strategy_id:
            msg = (
                f"Strategy mismatch: intent={intent_record.strategy_id}, "
                f"command={command.strategy_id}"
            )
            raise AppCommandError(msg)

        if intent_record.instrument_id != command.instrument_id:
            msg = (
                f"Instrument mismatch: intent={intent_record.instrument_id}, "
                f"command={command.instrument_id}"
            )
            raise AppCommandError(msg)

        if intent_record.direction != command.direction:
            msg = (
                f"Direction mismatch: intent={intent_record.direction}, "
                f"command={command.direction}"
            )
            raise AppCommandError(msg)

        if intent_record.status not in {"pending", "partially_filled", "filled"}:
            msg = (
                f"Intent {command.intent_id} status is '{intent_record.status}', "
                "expected 'pending', 'partially_filled', or 'filled'"
            )
            raise AppCommandError(msg)

    @staticmethod
    def _build_fill_dto(
        command: RecordFillCommand,
        tracker: ManualTracker,
    ) -> ManualExecutionFill:
        """构建 ManualExecutionFill DTO（含交收日期计算）."""
        settlement_date = tracker.compute_settlement_date(command.trade_date)
        return ManualExecutionFill(
            fill_id=command.fill_id,
            intent_id=command.intent_id,
            strategy_id=command.strategy_id,
            trade_date=command.trade_date,
            instrument_id=command.instrument_id,
            direction=command.direction,
            quantity=command.quantity,
            fill_price=command.fill_price,
            fee=command.fee,
            slippage=command.slippage,
            notes=command.notes,
            settlement_date=settlement_date,
        )


class _FillAdjustmentHandler:
    """Shared append-only correction orchestration."""

    def __init__(
        self,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        position_port: PositionDataPort,
        manual_tracker: ManualTracker,
        opening_baseline_resolver: OpeningBaselinePort,
    ) -> None:
        self._intent = intent_port
        self._fill = fill_port
        self._position = position_port
        self._tracker = manual_tracker
        self._opening_baseline = opening_baseline_resolver

    def _require_source_and_intent(
        self,
        fill_id: str,
    ) -> tuple[FillRecord, SignalRecord]:
        source = self._fill.get_fill(fill_id)
        if source is None:
            raise AppNotFoundError(f"Fill not found: {fill_id}")
        intent = self._intent.get_intent(source.intent_id)
        if intent is None:
            raise AppNotFoundError(f"Intent not found: {source.intent_id}")
        if (
            intent.strategy_id != source.strategy_id
            or intent.instrument_id != source.instrument_id
            or intent.direction != source.direction
        ):
            raise AppCommandError(f"Fill identity mismatch: {fill_id}")
        return source, intent

    def _apply(
        self,
        *,
        adjustment: FillAdjustmentRecord,
        source: FillRecord,
        intent: SignalRecord,
        replacement: FillRecord | None,
    ) -> bool:
        changed_date = min(
            source.trade_date,
            replacement.trade_date if replacement is not None else source.trade_date,
        )
        try:
            with self._fill.ledger_transaction():
                created = self._fill.apply_fill_adjustment(
                    adjustment,
                    replacement_fill=replacement,
                )
                if created is False:
                    return False
                locked_intent = self._intent.get_intent(intent.intent_id)
                if locked_intent is None:
                    raise AppNotFoundError(f"Intent not found: {intent.intent_id}")
                if (
                    locked_intent.strategy_id != source.strategy_id
                    or locked_intent.instrument_id != source.instrument_id
                    or locked_intent.direction != source.direction
                ):
                    raise AppCommandError(f"Fill identity mismatch: {source.fill_id}")
                effective = self._fill.list_effective_fills(
                    locked_intent.strategy_id,
                    intent_id=locked_intent.intent_id,
                )
                new_status = _effective_intent_status(
                    locked_intent.quantity,
                    effective,
                )
                updated = self._intent.update_intent_status(
                    locked_intent.intent_id,
                    new_status,
                    expected_current=(locked_intent.status,),
                )
                if not updated:
                    msg = (
                        "Concurrent fill adjustment conflict: "
                        f"{locked_intent.intent_id}"
                    )
                    raise AppConflictError(msg)
                _rebuild_manual_positions(
                    fill_port=self._fill,
                    position_port=self._position,
                    tracker=self._tracker,
                    intent=locked_intent,
                    changed_date=changed_date,
                    opening_baseline_resolver=self._opening_baseline,
                )
        except FillConflictError as exc:
            raise AppConflictError(str(exc)) from exc
        except FillNotFoundError as exc:
            raise AppNotFoundError(str(exc)) from exc
        except FillProcessingError as exc:
            raise AppCommandError(str(exc)) from exc
        return True


class ProjectedFillCorrectionAdapter(_FillAdjustmentHandler):
    """Reconciliation adapter that preserves ledger and derived projections."""

    def apply_projected_fill_replacement(
        self,
        *,
        adjustment: FillAdjustmentRecord,
        replacement_fill: FillRecord,
    ) -> bool:
        """Apply one deterministic replacement and rebuild status/positions."""
        if adjustment.adjustment_type != "replace":
            raise AppCommandError("Projected correction requires replace adjustment")
        if adjustment.replacement_fill_id != replacement_fill.fill_id:
            raise AppCommandError("Replacement fill ID does not match adjustment")
        source, intent = self._require_source_and_intent(adjustment.fill_id)
        return self._apply(
            adjustment=adjustment,
            source=source,
            intent=intent,
            replacement=replacement_fill,
        )


class VoidFillHandler(_FillAdjustmentHandler):
    """Append a void event and rebuild status/positions from effective fills."""

    def handle(self, command: VoidFillCommand) -> FillAdjustment:
        """Void one fill without mutating or deleting the original row."""
        existing = self._fill.get_fill_adjustment(command.adjustment_id)
        if existing is not None:
            if (
                existing.adjustment_type == "void"
                and existing.fill_id == command.fill_id
                and existing.replacement_fill_id is None
                and existing.reason == command.reason
            ):
                return record_to_adjustment(existing)
            raise AppConflictError(
                f"Fill adjustment ID conflict: {command.adjustment_id}"
            )
        if not command.reason.strip():
            raise AppCommandError("Fill adjustment reason is required")
        source, intent = self._require_source_and_intent(command.fill_id)
        adjustment = FillAdjustmentRecord(
            adjustment_id=command.adjustment_id,
            fill_id=command.fill_id,
            adjustment_type="void",
            replacement_fill_id=None,
            reason=command.reason,
            created_at=_utc_now(),
        )
        created = self._apply(
            adjustment=adjustment,
            source=source,
            intent=intent,
            replacement=None,
        )
        if not created:
            canonical = self._fill.get_fill_adjustment(command.adjustment_id)
            if canonical is None:
                raise AppNotFoundError(
                    f"Fill adjustment not found after replay: {command.adjustment_id}"
                )
            return record_to_adjustment(canonical)
        return record_to_adjustment(adjustment)


class ReplaceFillHandler(_FillAdjustmentHandler):
    """Append one replacement fill and its immutable correction event."""

    def handle(self, command: ReplaceFillCommand) -> FillAdjustment:
        """Replace one effective fill through append-only ledger evidence."""
        existing = self._fill.get_fill_adjustment(command.adjustment_id)
        if existing is not None:
            if self._same_existing_request(existing, command):
                return record_to_adjustment(existing)
            raise AppConflictError(
                f"Fill adjustment ID conflict: {command.adjustment_id}"
            )
        self._validate_command(command)
        source, intent = self._require_source_and_intent(command.fill_id)
        replacement = FillRecord(
            fill_id=command.replacement_fill_id,
            intent_id=source.intent_id,
            strategy_id=source.strategy_id,
            trade_date=command.trade_date,
            instrument_id=source.instrument_id,
            direction=source.direction,
            quantity=command.quantity,
            fill_price=command.fill_price,
            fee=command.fee,
            slippage=command.slippage,
            notes=command.notes,
            settlement_date=self._tracker.compute_settlement_date(command.trade_date),
            created_at=_utc_now(),
        )
        adjustment = FillAdjustmentRecord(
            adjustment_id=command.adjustment_id,
            fill_id=command.fill_id,
            adjustment_type="replace",
            replacement_fill_id=command.replacement_fill_id,
            reason=command.reason,
            created_at=_utc_now(),
        )
        created = self._apply(
            adjustment=adjustment,
            source=source,
            intent=intent,
            replacement=replacement,
        )
        if not created:
            canonical = self._fill.get_fill_adjustment(command.adjustment_id)
            if canonical is None:
                raise AppNotFoundError(
                    f"Fill adjustment not found after replay: {command.adjustment_id}"
                )
            return record_to_adjustment(canonical)
        return record_to_adjustment(adjustment)

    def _same_existing_request(
        self,
        existing: FillAdjustmentRecord,
        command: ReplaceFillCommand,
    ) -> bool:
        if (
            existing.adjustment_type != "replace"
            or existing.fill_id != command.fill_id
            or existing.replacement_fill_id != command.replacement_fill_id
            or existing.reason != command.reason
        ):
            return False
        replacement = self._fill.get_fill(command.replacement_fill_id)
        return replacement is not None and (
            replacement.trade_date == command.trade_date
            and replacement.quantity == command.quantity
            and replacement.fill_price == command.fill_price
            and replacement.fee == command.fee
            and replacement.slippage == command.slippage
            and replacement.notes == command.notes
        )

    @staticmethod
    def _validate_command(command: ReplaceFillCommand) -> None:
        if not command.reason.strip():
            raise AppCommandError("Fill adjustment reason is required")
        if command.quantity <= 0:
            raise AppCommandError("Replacement fill quantity must be positive")
        if not isfinite(command.fill_price) or command.fill_price <= 0.0:
            raise AppCommandError("Replacement fill price must be positive and finite")
        if not isfinite(command.fee) or command.fee < 0.0:
            raise AppCommandError(
                "Replacement fill fee must be non-negative and finite"
            )
        if not isfinite(command.slippage):
            raise AppCommandError("Replacement fill slippage must be finite")


def _effective_intent_status(
    intent_quantity: int | None,
    fills: list[FillRecord],
) -> str:
    total_quantity = sum(fill.quantity for fill in fills)
    if total_quantity == 0:
        return "pending"
    if intent_quantity is not None and total_quantity >= intent_quantity:
        return "filled"
    return "partially_filled"


def _validate_fill_identity(
    intent: SignalRecord | None,
    fill: FillRecord,
) -> None:
    if intent is None:
        raise AppNotFoundError(f"Intent not found: {fill.intent_id}")
    if (
        intent.strategy_id != fill.strategy_id
        or intent.instrument_id != fill.instrument_id
        or intent.direction != fill.direction
    ):
        raise AppCommandError(f"Fill identity mismatch: {fill.fill_id}")
    if intent.status not in {"pending", "partially_filled", "filled"}:
        msg = f"Intent {intent.intent_id} status is '{intent.status}', "
        msg += "expected 'pending', 'partially_filled', or 'filled'"
        raise AppCommandError(msg)


def _rebuild_manual_positions(
    *,
    fill_port: FillDataPort,
    position_port: PositionDataPort,
    tracker: ManualTracker,
    intent: SignalRecord,
    changed_date: str,
    opening_baseline_resolver: OpeningBaselinePort,
) -> None:
    strategy_id = intent.strategy_id
    baseline = opening_baseline_resolver.resolve(intent)
    opening_date = baseline.account.snapshot_date
    if changed_date <= opening_date:
        msg = "Manual fill date must be later than its opening baseline: "
        msg += f"fill={changed_date}, baseline={opening_date}"
        raise AppCommandError(msg)
    opening_positions = tuple(
        record_to_snapshot(position) for position in baseline.positions
    )

    existing_dates = {
        position.snapshot_date
        for position in position_port.list_positions(strategy_id, run_id="")
        if position.snapshot_date >= changed_date
    }
    raw_fill_dates = {
        fill.trade_date
        for fill in fill_port.list_fills(strategy_id)
        if fill.trade_date >= changed_date and fill.trade_date > opening_date
    }
    rebuild_dates = tuple(sorted({changed_date, *existing_dates, *raw_fill_dates}))
    effective = [
        record_to_fill(fill)
        for fill in fill_port.list_effective_fills(
            strategy_id,
            end_date=rebuild_dates[-1],
        )
        if fill.trade_date > opening_date
    ]
    for rebuild_date in rebuild_dates:
        positions = tracker.compute_positions(
            fills=effective,
            strategy_id=strategy_id,
            snapshot_date=rebuild_date,
            opening_positions=opening_positions,
        )
        position_port.replace_position_snapshot(
            strategy_id=strategy_id,
            snapshot_date=rebuild_date,
            positions=tuple(snapshot_to_record(position) for position in positions),
        )


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class UpdateIntentStatusHandler:
    """更新意图状态 — Command Handler."""

    def __init__(self, intent_port: IntentDataPort) -> None:
        self._intent = intent_port

    def handle(self, command: UpdateIntentStatusCommand) -> bool:
        """验证 intent 存在后更新状态（含合法性校验）."""
        intent = self._intent.get_intent(command.intent_id)
        if intent is None:
            msg = f"Intent not found: {command.intent_id}"
            raise AppCommandError(msg)

        # 合法状态枚举校验
        if command.status not in _VALID_INTENT_STATUSES:
            msg = f"Invalid status: {command.status}"
            raise AppCommandError(msg)

        # 状态转换矩阵校验
        allowed = _VALID_TRANSITIONS.get(intent.status, set())
        if command.status not in allowed and intent.status != command.status:
            msg = (
                f"Invalid transition: '{intent.status}' -> '{command.status}'. "
                f"Allowed: {allowed or '(terminal)'}"
            )
            raise AppCommandError(msg)

        # SQL 层状态前置条件：仅当当前状态在允许转换集合内时才更新
        expected = _VALID_TRANSITIONS.get(intent.status, set())
        # 幂等：status == status 时也允许（expected 可能为空集，此时用当前状态）
        if command.status == intent.status:
            expected = (intent.status,)
        # 终态（空转换集）时，用当前状态作为守卫条件以防止 lost-update
        if not expected:
            expected = (intent.status,)
        updated = self._intent.update_intent_status(
            command.intent_id,
            command.status,
            expected_current=tuple(expected),
        )
        if not updated:
            msg = (
                f"Concurrent status conflict: intent {command.intent_id} "
                f"was updated by another request"
            )
            raise AppCommandError(msg)
        return True
