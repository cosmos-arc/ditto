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

from ditto_application.exceptions import AppProcessError
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
        if sizing_contexts:
            intents = self._generate_sized_intents(
                strategy_id=strategy_id,
                signal_date=signal_date,
                target=target,
                threshold=threshold,
                sizing_contexts=sizing_contexts,
            )
        else:
            current_positions = self._position_reader.get_current_positions(strategy_id)
            intents = _generate_weight_intents(
                strategy_id=strategy_id,
                signal_date=signal_date,
                target=target,
                threshold=threshold,
                current_positions=current_positions,
            )

        # 可选推送信号
        if intents and self._signal_delivery is not None:
            self._signal_delivery.send_signal(strategy_id, intents)

        return intents

    def _generate_sized_intents(
        self,
        *,
        strategy_id: str,
        signal_date: str,
        target: TargetPortfolioLike,
        threshold: float,
        sizing_contexts: Mapping[int, ManualSizingContext],
    ) -> list[TradeIntent]:
        """Use D-price weights for thresholding and planner output for side/quantity."""
        sizing_service = self._sizing_service
        if sizing_service is None:
            raise AppProcessError("sizing service is required for sized intents")
        remaining_cash = _shared_cash_available(sizing_contexts)
        all_instruments = set(target.positions) | set(sizing_contexts)
        intents: list[TradeIntent] = []
        for iid in sorted(all_instruments, key=int):
            instrument_id = int(iid)
            context = sizing_contexts.get(instrument_id)
            target_weight = float(
                target.positions.get(InstrumentId(instrument_id), 0.0)
            )
            current_weight = _current_weight(context)
            delta_weight = target_weight - current_weight
            if context is None:
                if abs(delta_weight) > threshold:
                    intents.append(
                        _new_intent(
                            strategy_id,
                            signal_date,
                            instrument_id,
                            target_weight,
                            current_weight,
                        )
                    )
                continue
            provisional = _new_intent(
                strategy_id,
                signal_date,
                instrument_id,
                target_weight,
                current_weight,
            )
            sizing = sizing_service.size_intent(
                provisional,
                replace(
                    context,
                    cash_available=min(context.cash_available, remaining_cash),
                ),
            )
            if sizing.direction is None or abs(delta_weight) <= threshold:
                continue
            if sizing.direction == "buy":
                remaining_cash = max(0.0, remaining_cash - sizing.cash_required)
            intents.append(
                replace(
                    provisional,
                    direction=sizing.direction,
                    quantity=sizing.rounded_quantity,
                    raw_quantity=sizing.raw_quantity,
                    rounded_quantity=sizing.rounded_quantity,
                    lot_size=sizing.lot_size,
                    reference_price=sizing.reference_price,
                    cash_impact=sizing.cash_impact,
                    sizing_reason=sizing.reason,
                    sizing_readiness=sizing.readiness,
                )
            )
        return intents


def _shared_cash_available(
    sizing_contexts: Mapping[int, ManualSizingContext],
) -> float:
    if not sizing_contexts:
        return 0.0
    return max(
        0.0,
        min(context.cash_available for context in sizing_contexts.values()),
    )


def _current_weight(
    context: ManualSizingContext | None,
) -> float:
    if context is None:
        return 0.0
    if (
        context.reference_price is not None
        and context.reference_price > 0
        and context.nav > 0
    ):
        return context.current_quantity * context.reference_price / context.nav
    if context.current_weight is not None:
        return context.current_weight
    return 0.0


def _new_intent(
    strategy_id: str,
    signal_date: str,
    instrument_id: int,
    target_weight: float,
    current_weight: float,
) -> TradeIntent:
    delta_weight = target_weight - current_weight
    return TradeIntent(
        intent_id=uuid.uuid4().hex,
        strategy_id=strategy_id,
        signal_date=signal_date,
        instrument_id=instrument_id,
        direction="buy" if delta_weight > 0 else "sell",
        target_weight=target_weight,
        current_weight=current_weight,
        delta_weight=delta_weight,
    )


def _generate_weight_intents(
    *,
    strategy_id: str,
    signal_date: str,
    target: TargetPortfolioLike,
    threshold: float,
    current_positions: Mapping[int, float],
) -> list[TradeIntent]:
    all_instruments = set(target.positions) | set(current_positions)
    intents: list[TradeIntent] = []
    for iid in sorted(all_instruments, key=int):
        instrument_id = int(iid)
        target_weight = float(target.positions.get(InstrumentId(instrument_id), 0.0))
        current_weight = float(current_positions.get(instrument_id, 0.0))
        if abs(target_weight - current_weight) > threshold:
            intents.append(
                _new_intent(
                    strategy_id,
                    signal_date,
                    instrument_id,
                    target_weight,
                    current_weight,
                )
            )
    return intents
