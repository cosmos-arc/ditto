"""成交录入命令 DTO + Handler — 录入人工成交、更新交易意图状态."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.services.trade_service import TradeService

from ditto_app.process.execution.manual_tracker import ManualTracker
from ditto_app.types import (
    ManualExecutionFill,
    fill_to_record,
    record_to_fill,
    snapshot_to_record,
)

__all__ = [
    "RecordFillCommand",
    "RecordFillHandler",
    "UpdateIntentStatusCommand",
    "UpdateIntentStatusHandler",
]


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

        1. 验证 intent_id 有效
        2. 构建 ManualExecutionFill DTO
        3. 映射为 Record 并持久化
        4. 更新 intent 状态
        5. 触发 ManualTracker 重新聚合 → 更新持仓
        """
        # 1. 验证 intent 存在
        intent_record = self._service.get_intent(command.intent_id)
        if intent_record is None:
            msg = f"Intent not found: {command.intent_id}"
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

        # 4. 更新 intent 状态
        self._service.update_intent_status(command.intent_id, "filled")

        # 5. 触发 ManualTracker 重新聚合
        self._recompute_positions(command.strategy_id, command.trade_date)

        return fill

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
        """验证 intent 存在后更新状态."""
        intent = self._service.get_intent(command.intent_id)
        if intent is None:
            msg = f"Intent not found: {command.intent_id}"
            raise ValueError(msg)

        self._service.update_intent_status(command.intent_id, command.status)
        return True
