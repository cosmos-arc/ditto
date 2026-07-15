"""
SignalSnapshotProcess — 信号快照 + 交易意图推导.

从 Pipeline 输出的 TargetPortfolio 生成信号快照，
对比当前持仓推导出交易意图列表（TradeIntent）。

职责：
  1. 遍历 target.positions 获取所有目标 instrument_id
  2. 检查 current_positions 中有但 target 中没有的（需要清仓）
  3. 计算 delta_weight = target_weight - current_weight
  4. abs(delta_weight) > threshold 时生成 TradeIntent
  5. 可选推送信号通知（SignalDeliveryProtocol）
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace

from ditto_execution.targets import TargetPortfolioLike
from ditto_kernel.identity import InstrumentId

from ditto_application.execution_dto import TradeIntent
from ditto_application.processes.execution.manual_sizing import (
    ManualSizingContext,
    ManualSizingService,
)
from ditto_application.processes.execution.ports import (
    PositionReader,
    SignalDeliveryProtocol,
)

__all__ = ["SignalSnapshotProcess"]


class SignalSnapshotProcess:
    """从 Pipeline TargetPortfolio 生成信号快照 + 交易意图."""

    def __init__(
        self,
        position_reader: PositionReader,
        signal_delivery: SignalDeliveryProtocol | None = None,
        sizing_service: ManualSizingService | None = None,
    ) -> None:
        self._position_reader = position_reader
        self._signal_delivery = signal_delivery
        self._sizing_service = sizing_service

    def generate_intents(
        self,
        strategy_id: str,
        signal_date: str,
        target: TargetPortfolioLike,
        threshold: float = 0.01,
        sizing_contexts: Mapping[int, ManualSizingContext] | None = None,
    ) -> list[TradeIntent]:
        """
        对比目标组合与当前持仓，生成交易意图列表.

        Args:
            strategy_id: 策略 ID.
            signal_date: 信号日期 (YYYY-MM-DD).
            target: Pipeline 输出的目标组合.
            threshold: delta_weight 阈值，低于此值不生成 intent.
            sizing_contexts: 可选的逐标的账户、行情和交易规则上下文.

        Returns:
            需要调整的交易意图列表.

        """
        current_positions = self._position_reader.get_current_positions(strategy_id)

        # 收集所有涉及的 instrument_id（target + current 并集）
        all_instrument_ids = set(target.positions.keys()) | set(
            current_positions.keys(),
        )

        intents: list[TradeIntent] = []
        for iid in all_instrument_ids:
            iid_int = int(iid)
            target_weight = float(target.positions.get(InstrumentId(iid_int), 0.0))
            current_weight = float(current_positions.get(iid_int, 0.0))

            delta_weight = target_weight - current_weight

            if abs(delta_weight) > threshold:
                direction = "buy" if delta_weight > 0 else "sell"
                intent = TradeIntent(
                    intent_id=uuid.uuid4().hex,
                    strategy_id=strategy_id,
                    signal_date=signal_date,
                    instrument_id=iid_int,
                    direction=direction,
                    target_weight=target_weight,
                    current_weight=current_weight,
                    delta_weight=delta_weight,
                )
                context = (sizing_contexts or {}).get(iid_int)
                if self._sizing_service is not None and context is not None:
                    sizing = self._sizing_service.size_intent(intent, context)
                    intent = replace(intent, quantity=sizing.rounded_quantity)
                intents.append(intent)

        # 可选推送信号
        if intents and self._signal_delivery is not None:
            self._signal_delivery.send_signal(strategy_id, intents)

        return intents
