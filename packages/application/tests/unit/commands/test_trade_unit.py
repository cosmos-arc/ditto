"""TradeCommandHandler 单元测试 — 成交录入命令处理."""

from __future__ import annotations

from unittest.mock import MagicMock

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
    mock = MagicMock(spec=["find_fill", "save_fill", "list_fills"])
    mock.find_fill.return_value = None
    return mock


def _make_position_port() -> MagicMock:
    """构建 PositionDataPort mock."""
    return MagicMock(spec=["save_position", "list_positions"])


def _make_manual_tracker() -> MagicMock:
    """构建 ManualTracker mock，暴露 compute_positions + compute_settlement_date."""
    return MagicMock(spec=["compute_positions", "compute_settlement_date"])


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
        """幂等性: 相同 intent_id + trade_date 已有 fill 时直接返回已有记录."""
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
        fill_port.find_fill.return_value = existing_record

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
        )

        cmd = RecordFillCommand(
            fill_id="fill-new-duplicate",
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
        fill_port.list_fills.return_value = [new_fill_record]

        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
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
            expected_current=("pending", "partially_filled"),
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
        fill_port.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
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
        fill_port.list_fills.return_value = []

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

        position_port.save_position.assert_called_once()
        saved_pos = position_port.save_position.call_args[0][0]
        assert saved_pos.snapshot_id == "snap-001"
        assert saved_pos.quantity == 1000

    def test_handle_computes_settlement_date(self) -> None:
        """handler 调用 compute_settlement_date 并将结果传入 DTO."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent_port.get_intent.return_value = _make_intent_record()
        fill_port.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
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
        fill_port.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-11"

        handler = RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
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
        ) or set(call_kwargs["expected_current"]) == {
            "filled",
            "partially_filled",
            "cancelled",
            "expired",
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
        fill_port.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"
        return RecordFillHandler(
            intent_port=intent_port,
            fill_port=fill_port,
            position_port=position_port,
            manual_tracker=tracker,
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
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
        )

    def test_fill_quantity_less_than_intent_returns_partial(self) -> None:
        """fill_quantity < intent_quantity → 状态更新为 partially_filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
        )

    def test_fill_quantity_exceeds_intent_returns_filled(self) -> None:
        """fill_quantity > intent_quantity → 仍更新为 filled（超额成交）."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        intent_port.get_intent.return_value = intent
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
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
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
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
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
        )

    def test_none_intent_quantity_returns_partial(self) -> None:
        """intent_quantity 为 None 时始终返回 partially_filled，不自动标记 filled."""

        intent_port = _make_intent_port()
        fill_port = _make_fill_port()
        position_port = _make_position_port()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=None)
        intent_port.get_intent.return_value = intent
        fill_port.list_fills.return_value = [
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
            expected_current=("pending", "partially_filled"),
        )

    def test_fill_on_terminal_intent_rejected(self) -> None:
        """intent 状态为 filled/cancelled/expired 时，拒绝录入成交."""

        for terminal_status in ("filled", "cancelled", "expired"):
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
                AppCommandError, match="expected 'pending' or 'partially_filled'"
            ):
                handler.handle(cmd)

            fill_port.save_fill.assert_not_called()
            intent_port.update_intent_status.assert_not_called()


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
