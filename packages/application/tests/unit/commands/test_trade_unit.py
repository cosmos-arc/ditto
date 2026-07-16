"""TradeCommandHandler 单元测试 — 成交录入命令处理."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import ditto_application.commands.trade as trade_commands
import pytest
from ditto_application.commands.protocols import CommandHandler
from ditto_application.commands.trade import (
    RecordFillCommand,
    RecordFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.execution_dto import ActualPositionSnapshot, ManualExecutionFill
from ditto_execution.models import (
    FillAdjustmentRecord,
    FillRecord,
    SignalRecord,
)


def _make_intent_port() -> MagicMock:
    """构建 IntentDataPort mock."""
    return MagicMock(
        spec=["get_intent", "update_intent_status", "save_intent", "list_intents"]
    )


def _make_fill_port() -> MagicMock:
    """构建 FillDataPort mock."""
    mock = MagicMock(
        spec=[
            "apply_fill_adjustment",
            "get_fill",
            "get_fill_adjustment",
            "ledger_transaction",
            "list_effective_fills",
            "list_fill_adjustments",
            "list_fills",
            "save_fill",
        ]
    )
    mock.get_fill.return_value = None
    return mock


def _make_position_port() -> MagicMock:
    """构建 PositionDataPort mock."""
    return MagicMock(
        spec=["list_positions", "replace_position_snapshot", "save_position"]
    )


def _make_manual_tracker() -> MagicMock:
    """构建 ManualTracker mock，暴露 compute_positions + compute_settlement_date."""
    return MagicMock(spec=["compute_positions", "compute_settlement_date"])


def _make_opening_baseline_resolver() -> MagicMock:
    """构建显式 opening baseline port；命令测试不允许隐式零基线。"""
    resolver = MagicMock(spec=["resolve"])
    resolver.resolve.return_value = MagicMock(
        account=MagicMock(snapshot_date="1900-01-01"),
        positions=(),
    )
    return resolver


def _make_intent_record(**overrides: object) -> SignalRecord:
    """构建测试用 SignalRecord."""
    defaults: dict[str, object] = {
        "intent_id": "intent-001",
        "strategy_id": "strat-alpha",
        "signal_date": "2026-04-10",
        "instrument_id": 510050,
        "direction": "buy",
        "target_weight": 0.3,
        "current_weight": 0.1,
        "delta_weight": 0.2,
        "quantity": 1000,
        "status": "pending",
        "created_at": "2026-04-10T09:30:00Z",
    }
    defaults.update(overrides)
    return SignalRecord(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RecordFillHandler
# ---------------------------------------------------------------------------


class TestRecordFillHandler:
    """RecordFillHandler — 录入人工成交."""

    def test_idempotent_returns_existing_fill(self) -> None:
        """幂等性: 相同 fill_id + 相同请求 payload 直接返回已有记录."""
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        existing_record = FillRecord(
            fill_id="fill-existing",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )
        fill_port.get_fill.return_value = existing_record

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-existing",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )

        result = handler.handle(cmd)

        assert isinstance(result, ManualExecutionFill)
        assert result.fill_id == "fill-existing"

        fill_port.save_fill.assert_not_called()
        intent_port.update_intent_status.assert_not_called()
        tracker.compute_positions.assert_not_called()

    def test_same_intent_and_trade_date_records_second_fill_id(self) -> None:
        """同 intent/date 的新 fill_id 是新的部分成交，不得返回第一笔。"""
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = _make_intent_record(
            quantity=1000,
            status="partially_filled",
        )
        first = FillRecord(
            fill_id="fill-part-1",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=300,
            fill_price=4.10,
            fee=1.0,
        )
        second = FillRecord(
            fill_id="fill-part-2",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=200,
            fill_price=4.15,
            fee=1.0,
        )
        fill_port.list_effective_fills.return_value = [first, second]
        position_port.list_positions.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"
        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        result = handler.handle(
            RecordFillCommand(
                fill_id="fill-part-2",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=200,
                fill_price=4.15,
                fee=1.0,
            )
        )

        assert result.fill_id == "fill-part-2"
        fill_port.save_fill.assert_called_once()
        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("partially_filled",),
        )

    def test_handle_saves_fill_and_updates_intent(self) -> None:
        """成功录入 → fill 持久化 + intent 状态更新为 filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record()
        intent_port.get_intent.return_value = intent

        new_fill_record = FillRecord(
            fill_id="fill-001",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )
        fill_port.list_effective_fills.return_value = [new_fill_record]

        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-001",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )

        result = handler.handle(cmd)

        assert isinstance(result, ManualExecutionFill)
        assert result.fill_id == "fill-001"
        assert result.intent_id == "intent-001"
        assert result.quantity == 1000
        assert result.fill_price == 4.15

        fill_port.save_fill.assert_called_once()
        saved_record = fill_port.save_fill.call_args[0][0]
        assert isinstance(saved_record, FillRecord)
        assert saved_record.fill_id == "fill-001"

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
            expected_current=("pending",),
        )

        tracker.compute_positions.assert_called_once()

    def test_handle_raises_on_missing_intent(self) -> None:
        """intent 不存在 → ValueError."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = None

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-002",
            intent_id="intent-missing",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=500,
            fill_price=4.10,
            fee=2.5,
        )

        with pytest.raises(AppCommandError, match="Intent not found: intent-missing"):
            handler.handle(cmd)

        fill_port.save_fill.assert_not_called()
        intent_port.update_intent_status.assert_not_called()

    def test_handle_with_default_values(self) -> None:
        """带默认值 → fee/slippage/notes 正确传递."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_effective_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-003",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=200,
            fill_price=4.20,
        )

        result = handler.handle(cmd)

        assert result.fee == 0.0
        assert result.slippage == 0.0
        assert result.notes == ""

        saved_record = fill_port.save_fill.call_args[0][0]
        assert saved_record.fee == 0.0
        assert saved_record.slippage == 0.0
        assert saved_record.notes == ""

    def test_handle_triggers_tracker_recomputation(self) -> None:
        """录入成交后触发 ManualTracker 重新聚合持仓并持久化."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_effective_fills.return_value = []

        snapshot = ActualPositionSnapshot(
            snapshot_id="snap-001",
            strategy_id="strat-alpha",
            snapshot_date="2026-04-11",
            instrument_id=510050,
            quantity=1000,
            available_quantity=0,
            average_cost=4.15,
            market_value=0.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        tracker.compute_positions.return_value = [snapshot]
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-004",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )

        handler.handle(cmd)

        tracker.compute_positions.assert_called_once()
        call_kwargs = tracker.compute_positions.call_args
        assert call_kwargs[1]["strategy_id"] == "strat-alpha"
        assert call_kwargs[1]["snapshot_date"] == "2026-04-11"

        position_port.replace_position_snapshot.assert_called_once()
        saved_pos = position_port.replace_position_snapshot.call_args.kwargs[
            "positions"
        ][0]
        assert saved_pos.snapshot_id == "snap-001"
        assert saved_pos.quantity == 1000

    def test_handle_computes_settlement_date(self) -> None:
        """handler 调用 compute_settlement_date 并将结果传入 DTO."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_effective_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-005",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )

        result = handler.handle(cmd)

        tracker.compute_settlement_date.assert_called_once_with("2026-04-11")

        assert result.settlement_date == "2026-04-14"

        saved_record = fill_port.save_fill.call_args[0][0]
        assert saved_record.settlement_date == "2026-04-14"

    def test_handle_settlement_date_fallback(self) -> None:
        """tracker 返回空日历时 settlement_date fallback 到 trade_date."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_effective_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-11"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        cmd = RecordFillCommand(
            fill_id="fill-006",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=500,
            fill_price=4.10,
        )

        result = handler.handle(cmd)

        assert result.settlement_date == "2026-04-11"

        saved_record = fill_port.save_fill.call_args[0][0]
        assert saved_record.settlement_date == "2026-04-11"


# ---------------------------------------------------------------------------
# UpdateIntentStatusHandler
# ---------------------------------------------------------------------------


class TestUpdateIntentStatusHandler:
    """UpdateIntentStatusHandler — 更新交易意图状态."""

    def test_handle_updates_status(self) -> None:
        """成功更新意图状态."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record()

        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="cancelled",
        )

        result = handler.handle(cmd)

        assert result is True
        intent_port.update_intent_status.assert_called_once()
        call_kwargs = intent_port.update_intent_status.call_args[1]
        assert call_kwargs["expected_current"] == (
            "filled",
            "partially_filled",
            "cancelled",
            "expired",
            "superseded",
        ) or set(call_kwargs["expected_current"]) == {
            "filled",
            "partially_filled",
            "cancelled",
            "expired",
            "superseded",
        }

    def test_handle_raises_on_missing_intent(self) -> None:
        """intent 不存在 → ValueError."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = None

        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-missing",
            status="cancelled",
        )

        with pytest.raises(AppCommandError, match="Intent not found: intent-missing"):
            handler.handle(cmd)

        intent_port.update_intent_status.assert_not_called()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestTradeCommandProtocolConformance:
    """所有 Trade Handler 满足 CommandHandler Protocol."""

    def test_record_fill_handler_satisfies_protocol(self) -> None:
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        assert isinstance(handler, CommandHandler)

    def test_update_intent_status_handler_satisfies_protocol(self) -> None:
        intent_port = _make_intent_port()
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        assert isinstance(handler, CommandHandler)


# ---------------------------------------------------------------------------
# Identity validation (T28)
# ---------------------------------------------------------------------------


class TestRecordFillIdentityValidation:
    """RecordFillHandler — 身份校验 (strategy_id / instrument_id / direction)."""

    def _make_handler(self):
        """构建 handler (不导入在类外, 避免顶层导入)."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_effective_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"
        return RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

    def test_strategy_id_mismatch_rejected(self) -> None:
        """command.strategy_id 与 intent.strategy_id 不一致 → ValueError."""

        handler = self._make_handler()
        cmd = RecordFillCommand(
            fill_id="fill-reject-1",
            intent_id="intent-001",
            strategy_id="wrong-strategy",  # 与 intent 的 strat-alpha 不匹配
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
        )

        with pytest.raises(AppCommandError, match="Strategy mismatch"):
            handler.handle(cmd)

    def test_instrument_id_mismatch_rejected(self) -> None:
        """command.instrument_id 与 intent.instrument_id 不一致 → ValueError."""

        handler = self._make_handler()
        cmd = RecordFillCommand(
            fill_id="fill-reject-2",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=999999,  # 与 intent 的 510050 不匹配
            direction="buy",
            quantity=1000,
            fill_price=4.15,
        )

        with pytest.raises(AppCommandError, match="Instrument mismatch"):
            handler.handle(cmd)

    def test_direction_mismatch_rejected(self) -> None:
        """command.direction 与 intent.direction 不一致 → ValueError."""

        handler = self._make_handler()
        cmd = RecordFillCommand(
            fill_id="fill-reject-3",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="sell",  # 与 intent 的 buy 不匹配
            quantity=1000,
            fill_price=4.15,
        )

        with pytest.raises(AppCommandError, match="Direction mismatch"):
            handler.handle(cmd)


# ---------------------------------------------------------------------------
# Partial fill detection (T28)
# ---------------------------------------------------------------------------


class TestRecordFillPartialFillDetection:
    """RecordFillHandler — 部分成交判断."""

    def test_fill_quantity_equals_intent_returns_filled(self) -> None:
        """fill_quantity == intent_quantity → 状态更新为 filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent
        fill_port.list_effective_fills.return_value = [
            FillRecord(
                fill_id="fill-full",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=1000,
                fill_price=4.15,
                fee=2.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-full",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
            expected_current=("pending",),
        )

    def test_fill_quantity_less_than_intent_returns_partial(self) -> None:
        """fill_quantity < intent_quantity → 状态更新为 partially_filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent
        fill_port.list_effective_fills.return_value = [
            FillRecord(
                fill_id="fill-partial",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=500,
                fill_price=4.15,
                fee=2.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-partial",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=500,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("pending",),
        )

    def test_fill_quantity_exceeds_intent_returns_filled(self) -> None:
        """fill_quantity > intent_quantity → 仍更新为 filled（超额成交）."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent
        fill_port.list_effective_fills.return_value = [
            FillRecord(
                fill_id="fill-over",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=1500,
                fill_price=4.15,
                fee=2.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-over",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1500,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
            expected_current=("pending",),
        )

    def test_cumulative_fills_reach_intent_quantity_returns_filled(self) -> None:
        """已有部分成交 + 新 fill 使累积量达到 intent 数量 → filled."""
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent

        existing_fill = FillRecord(
            fill_id="fill-prev",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=600,
            fill_price=4.10,
            fee=2.5,
        )
        fill_port.list_effective_fills.return_value = [
            existing_fill,
            FillRecord(
                fill_id="fill-new",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=400,
                fill_price=4.15,
                fee=2.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-new",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=400,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
            expected_current=("pending",),
        )

    def test_cumulative_fills_still_below_intent_returns_partial(self) -> None:
        """已有部分成交 + 新 fill 累积量仍低于 intent → partially_filled."""
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent

        existing_fill = FillRecord(
            fill_id="fill-prev",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=300,
            fill_price=4.10,
            fee=1.5,
        )
        fill_port.list_effective_fills.return_value = [
            existing_fill,
            FillRecord(
                fill_id="fill-new",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=200,
                fill_price=4.15,
                fee=1.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-new",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=200,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("pending",),
        )

    def test_none_intent_quantity_returns_partial(self) -> None:
        """intent_quantity 为 None 时始终返回 partially_filled，不自动标记 filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=None)
        intent_port.get_intent.return_value = intent
        fill_port.list_effective_fills.return_value = [
            FillRecord(
                fill_id="fill-none",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=1000,
                fill_price=4.15,
                fee=2.0,
            ),
        ]
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )
        cmd = RecordFillCommand(
            fill_id="fill-none",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
        )
        handler.handle(cmd)

        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("pending",),
        )

    def test_fill_on_closed_intent_rejected(self) -> None:
        """cancelled/expired/superseded intent rejects a new fill ID."""

        for terminal_status in ("cancelled", "expired", "superseded"):
            intent_port = _make_intent_port()
            fill_port = _make_fill_port()
            position_port = _make_position_port()
            tracker = _make_manual_tracker()

            intent = _make_intent_record(status=terminal_status)
            intent_port.get_intent.return_value = intent
            tracker.compute_settlement_date.return_value = "2026-04-14"

            handler = RecordFillHandler(
                intent_port=intent_port,
                fill_port=fill_port,
                position_port=position_port,
                manual_tracker=tracker,
                opening_baseline_resolver=_make_opening_baseline_resolver(),
            )
            cmd = RecordFillCommand(
                fill_id=f"fill-terminal-{terminal_status}",
                intent_id="intent-001",
                strategy_id="strat-alpha",
                trade_date="2026-04-11",
                instrument_id=510050,
                direction="buy",
                quantity=1000,
                fill_price=4.15,
            )

            with pytest.raises(
                AppCommandError,
                match="expected 'pending', 'partially_filled', or 'filled'",
            ):
                handler.handle(cmd)

            fill_port.save_fill.assert_not_called()
            intent_port.update_intent_status.assert_not_called()


class TestFillAdjustmentHandlers:
    """Append-only void/replace commands rebuild effective projections."""

    def test_void_reopens_filled_intent_from_effective_quantity(self) -> None:
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = _make_intent_record(
            quantity=1000,
            status="filled",
        )
        source = FillRecord(
            fill_id="fill-wrong",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=600,
            fill_price=4.15,
            fee=2.0,
        )
        remaining = FillRecord(
            fill_id="fill-still-effective",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=400,
            fill_price=4.10,
            fee=1.0,
        )
        fill_port.get_fill.return_value = source
        fill_port.get_fill_adjustment.return_value = None
        fill_port.list_effective_fills.return_value = [remaining]
        position_port.list_positions.return_value = []
        tracker.compute_positions.return_value = []
        handler = trade_commands.VoidFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        result = handler.handle(
            trade_commands.VoidFillCommand(
                adjustment_id="adj-void",
                fill_id=source.fill_id,
                reason="duplicate entry",
            )
        )

        assert result.adjustment_id == "adj-void"
        assert result.adjustment_type == "void"
        fill_port.apply_fill_adjustment.assert_called_once()
        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("filled",),
        )

    def test_replace_appends_new_fill_and_recomputes_partial_status(self) -> None:
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = _make_intent_record(
            quantity=1000,
            status="filled",
        )
        source = FillRecord(
            fill_id="fill-wrong",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,
            fill_price=4.15,
            fee=5.0,
        )
        effective_replacement = replace(
            source,
            fill_id="fill-corrected",
            quantity=400,
            fill_price=4.12,
            fee=2.0,
        )
        fill_port.get_fill.return_value = source
        fill_port.get_fill_adjustment.return_value = None
        fill_port.list_effective_fills.return_value = [effective_replacement]
        position_port.list_positions.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"
        handler = trade_commands.ReplaceFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        result = handler.handle(
            trade_commands.ReplaceFillCommand(
                adjustment_id="adj-replace",
                fill_id=source.fill_id,
                replacement_fill_id="fill-corrected",
                trade_date="2026-04-11",
                quantity=400,
                fill_price=4.12,
                fee=2.0,
                reason="correct broker quantity",
            )
        )

        assert result.adjustment_type == "replace"
        call = fill_port.apply_fill_adjustment.call_args
        replacement = call.kwargs["replacement_fill"]
        assert replacement.fill_id == "fill-corrected"
        assert replacement.quantity == 400
        assert replacement.intent_id == source.intent_id
        intent_port.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
            expected_current=("filled",),
        )

    def test_void_rebuilds_changed_and_all_later_position_dates(self) -> None:
        """A historical correction must replay every persisted later projection."""
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        intent_port.get_intent.return_value = _make_intent_record(
            quantity=1000,
            status="filled",
        )
        source = FillRecord(
            fill_id="fill-historical",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=800,
            fill_price=4.15,
            fee=2.0,
        )
        later_fill = replace(
            source,
            fill_id="fill-later",
            trade_date="2026-04-15",
            quantity=200,
        )
        fill_port.get_fill.return_value = source
        fill_port.get_fill_adjustment.return_value = None
        fill_port.list_fills.return_value = [source, later_fill]
        fill_port.list_effective_fills.return_value = [later_fill]
        prior_snapshot = MagicMock(snapshot_date="2026-04-13")
        position_port.list_positions.return_value = [prior_snapshot]
        tracker.compute_positions.return_value = []
        handler = trade_commands.VoidFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        handler.handle(
            trade_commands.VoidFillCommand(
                adjustment_id="adj-historical-void",
                fill_id=source.fill_id,
                reason="historical duplicate",
            )
        )

        assert [
            call.kwargs["snapshot_date"]
            for call in tracker.compute_positions.call_args_list
        ] == ["2026-04-11", "2026-04-13", "2026-04-15"]
        assert [
            call.kwargs["snapshot_date"]
            for call in position_port.replace_position_snapshot.call_args_list
        ] == ["2026-04-11", "2026-04-13", "2026-04-15"]
        for call in tracker.compute_positions.call_args_list:
            assert [fill.fill_id for fill in call.kwargs["fills"]] == [
                later_fill.fill_id
            ]

    def test_exact_void_adjustment_replay_is_noop(self) -> None:
        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()
        existing = FillAdjustmentRecord(
            adjustment_id="adj-existing",
            fill_id="fill-existing",
            adjustment_type="void",
            replacement_fill_id=None,
            reason="duplicate entry",
            created_at="2026-04-11T12:00:00Z",
        )
        fill_port.get_fill_adjustment.return_value = existing
        handler = trade_commands.VoidFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
            opening_baseline_resolver=_make_opening_baseline_resolver(),
        )

        result = handler.handle(
            trade_commands.VoidFillCommand(
                adjustment_id="adj-existing",
                fill_id="fill-existing",
                reason="duplicate entry",
            )
        )

        assert result.created_at == "2026-04-11T12:00:00Z"
        fill_port.apply_fill_adjustment.assert_not_called()
        intent_port.update_intent_status.assert_not_called()
        position_port.replace_position_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# Status transition matrix validation (T28)
# ---------------------------------------------------------------------------


class TestUpdateIntentStatusTransitions:
    """UpdateIntentStatusHandler — 状态转换矩阵校验."""

    def test_valid_transition_pending_to_cancelled(self) -> None:
        """pending → cancelled 合法."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="cancelled")

        assert handler.handle(cmd) is True

    def test_valid_transition_pending_to_filled(self) -> None:
        """pending → filled 合法."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        assert handler.handle(cmd) is True

    def test_valid_transition_partially_filled_to_filled(self) -> None:
        """partially_filled → filled 合法."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(
            status="partially_filled",
        )
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        assert handler.handle(cmd) is True

    def test_invalid_transition_filled_to_pending_rejected(self) -> None:
        """filled → pending 非法 (终态不可回退)."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="filled")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="pending")

        with pytest.raises(
            AppCommandError,
            match=r"Invalid transition.*filled.*pending",
        ):
            handler.handle(cmd)

    def test_invalid_transition_cancelled_to_filled_rejected(self) -> None:
        """cancelled → filled 非法."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="cancelled")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        with pytest.raises(AppCommandError, match="Invalid transition"):
            handler.handle(cmd)

    def test_invalid_transition_expired_to_partially_filled_rejected(self) -> None:
        """expired → partially_filled 非法."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="expired")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="partially_filled",
        )

        with pytest.raises(AppCommandError, match="Invalid transition"):
            handler.handle(cmd)

    def test_same_status_idempotent(self) -> None:
        """相同状态 idempotent: pending → pending 不报错."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="pending")

        assert handler.handle(cmd) is True

    def test_invalid_status_name_rejected(self) -> None:
        """非法状态名称 → ValueError."""

        intent_port = _make_intent_port()
        intent_port.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(intent_port=intent_port)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="invalid_status",
        )

        with pytest.raises(AppCommandError, match="Invalid status"):
            handler.handle(cmd)

        intent_port.update_intent_status.assert_not_called()
