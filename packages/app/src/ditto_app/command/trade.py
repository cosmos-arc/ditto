"""成交录入命令 DTO + Handler — 录入人工成交、更新交易意图状态."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ditto_data.services.trade_service import TradeService

from ditto_app.execution_dto import (
    ManualExecutionFill,
    fill_to_record,
    record_to_fill,
    snapshot_to_record,
)
from ditto_app.process.execution.manual_tracker import ManualTracker

__all__ = [
    "RecordFillCommand",
    "RecordFillHandler",
    "UpdateIntentStatusCommand",
    "UpdateIntentStatusHandler",
]

_VALID_INTENT_STATUSES = {
    "pending",
    "filled",
    "partially_filled",
    "cancelled",
    "expired",
}

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"filled", "partially_filled", "cancelled", "expired"},
    "partially_filled": {"filled", "partially_filled", "cancelled", "expired"},
    "filled": set(),  # terminal
    "cancelled": set(),  # terminal
    "expired": set(),  # terminal
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
class UpdateIntentStatusCommand:
    """更新交易意图状态命令."""

    intent_id: str
    status: str


class RecordFillHandler:
    """录入人工成交 — Command Handler."""

    def __init__(
        self,
        trade_service: TradeService,
        manual_tracker: ManualTracker,
    ) -> None:
        self._service = trade_service
        self._tracker = manual_tracker

    def handle(self, command: RecordFillCommand) -> ManualExecutionFill:
        """
        处理成交录入命令.

        1. 验证 intent_id 有效 + 身份校验
        2. 构建 ManualExecutionFill DTO
        3. 映射为 Record 并持久化
        4. 更新 intent 状态（支持部分成交）
        5. 触发 ManualTracker 重新聚合 → 更新持仓
        """
        # 1. 验证 intent 存在
        intent_record = self._service.get_intent(command.intent_id)
        if intent_record is None:
            msg = f"Intent not found: {command.intent_id}"
            raise ValueError(msg)

        # 身份校验：strategy_id / instrument_id / direction 必须一致
        if intent_record.strategy_id != command.strategy_id:
            msg = (
                f"Strategy mismatch: intent={intent_record.strategy_id}, "
                f"command={command.strategy_id}"
            )
            raise ValueError(msg)

        if intent_record.instrument_id != command.instrument_id:
            msg = (
                f"Instrument mismatch: intent={intent_record.instrument_id}, "
                f"command={command.instrument_id}"
            )
            raise ValueError(msg)

        if intent_record.direction != command.direction:
            msg = (
                f"Direction mismatch: intent={intent_record.direction}, "
                f"command={command.direction}"
            )
            raise ValueError(msg)

        # 状态校验：只允许 pending/partially_filled 状态录入成交
        if intent_record.status not in {"pending", "partially_filled"}:
            msg = (
                f"Intent {command.intent_id} status is '{intent_record.status}', "
                f"expected 'pending' or 'partially_filled'"
            )
            raise ValueError(msg)

        # 2. 构建 DTO（含交收日期）
        settlement_date = self._tracker.compute_settlement_date(command.trade_date)
        fill = ManualExecutionFill(
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

        # 3. 映射为 Record 并持久化
        record = fill_to_record(fill)
        self._service.save_fill(record)

        # 4. 更新 intent 状态（部分成交判断）
        new_status = self._determine_fill_status(
            intent_record.quantity, command.quantity
        )
        self._service.update_intent_status(command.intent_id, new_status)

        # 5. 触发 ManualTracker 重新聚合（使用 intent 的 strategy_id）
        self._recompute_positions(intent_record.strategy_id, command.trade_date)

        return fill

    @staticmethod
    def _determine_fill_status(
        intent_quantity: int | None,
        fill_quantity: int,
    ) -> Literal["filled", "partially_filled"]:
        """判断完全成交还是部分成交."""
        if intent_quantity is None or fill_quantity >= intent_quantity:
            return "filled"
        return "partially_filled"

    def _recompute_positions(self, strategy_id: str, snapshot_date: str) -> None:
        """重新聚合持仓并持久化."""
        fill_records = self._service.list_fills(strategy_id=strategy_id)
        fills = [record_to_fill(r) for r in fill_records]

        snapshots = self._tracker.compute_positions(
            fills=fills,
            strategy_id=strategy_id,
            snapshot_date=snapshot_date,
        )

        for snapshot in snapshots:
            self._service.save_position(snapshot_to_record(snapshot))


class UpdateIntentStatusHandler:
    """更新意图状态 — Command Handler."""

    def __init__(self, trade_service: TradeService) -> None:
        self._service = trade_service

    def handle(self, command: UpdateIntentStatusCommand) -> bool:
        """验证 intent 存在后更新状态（含合法性校验）."""
        intent = self._service.get_intent(command.intent_id)
        if intent is None:
            msg = f"Intent not found: {command.intent_id}"
            raise ValueError(msg)

        # 合法状态枚举校验
        if command.status not in _VALID_INTENT_STATUSES:
            msg = f"Invalid status: {command.status}"
            raise ValueError(msg)

        # 状态转换矩阵校验
        allowed = _VALID_TRANSITIONS.get(intent.status, set())
        if command.status not in allowed and intent.status != command.status:
            msg = (
                f"Invalid transition: '{intent.status}' -> '{command.status}'. "
                f"Allowed: {allowed or '(terminal)'}"
            )
            raise ValueError(msg)

        self._service.update_intent_status(command.intent_id, command.status)
        return True
