"""TradeCommandHandler 单元测试 — 成交录入命令处理."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_app.command.protocols import CommandHandler
from ditto_app.command.trade import (
    RecordFillCommand,
    RecordFillHandler,
    UpdateIntentStatusCommand,
    UpdateIntentStatusHandler,
)
from ditto_app.execution_dto import ActualPositionSnapshot, ManualExecutionFill
from ditto_data.models.trade import (
    ManualExecutionFillRecord,
    TradeIntentRecord,
)


def _make_trade_service() -> MagicMock:
    """构建 TradeService mock，包含成交录入所需公开方法."""
    return MagicMock(
        spec=[
            "get_intent",
            "save_fill",
            "update_intent_status",
            "list_fills",
            "save_position",
        ],
    )


def _make_manual_tracker() -> MagicMock:
    """构建 ManualTracker mock，暴露 compute_positions + compute_settlement_date."""
    return MagicMock(spec=["compute_positions", "compute_settlement_date"])


def _make_intent_record(**overrides: object) -> TradeIntentRecord:
    """构建测试用 TradeIntentRecord."""
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
    return TradeIntentRecord(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RecordFillHandler
# ---------------------------------------------------------------------------


class TestRecordFillHandler:
    """RecordFillHandler — 录入人工成交."""

    def test_handle_saves_fill_and_updates_intent(self) -> None:
        """成功录入 → fill 持久化 + intent 状态更新为 filled."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        intent = _make_intent_record()
        service.get_intent.return_value = intent

        # list_fills 返回空列表 + 新 fill 的 record
        new_fill_record = ManualExecutionFillRecord(
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
        service.list_fills.return_value = [new_fill_record]

        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            trade_service=service,
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

        # 验证返回 ManualExecutionFill DTO
        assert isinstance(result, ManualExecutionFill)
        assert result.fill_id == "fill-001"
        assert result.intent_id == "intent-001"
        assert result.quantity == 1000
        assert result.fill_price == 4.15

        # 验证 save_fill 被调用
        service.save_fill.assert_called_once()
        saved_record = service.save_fill.call_args[0][0]
        assert isinstance(saved_record, ManualExecutionFillRecord)
        assert saved_record.fill_id == "fill-001"

        # 验证 intent 状态更新为 filled
        service.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
        )

        # 验证 tracker 被调用
        tracker.compute_positions.assert_called_once()

    def test_handle_raises_on_missing_intent(self) -> None:
        """intent 不存在 → ValueError."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()
        service.get_intent.return_value = None

        handler = RecordFillHandler(
            trade_service=service,
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

        with pytest.raises(ValueError, match="Intent not found: intent-missing"):
            handler.handle(cmd)

        # 验证无副作用
        service.save_fill.assert_not_called()
        service.update_intent_status.assert_not_called()

    def test_handle_with_default_values(self) -> None:
        """带默认值 → fee/slippage/notes 正确传递."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        service.get_intent.return_value = _make_intent_record()
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            trade_service=service,
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
            # fee, slippage, notes 使用默认值
        )

        result = handler.handle(cmd)

        assert result.fee == 0.0
        assert result.slippage == 0.0
        assert result.notes == ""

        # 验证 save_fill 传递的 record 也包含默认值
        saved_record = service.save_fill.call_args[0][0]
        assert saved_record.fee == 0.0
        assert saved_record.slippage == 0.0
        assert saved_record.notes == ""

    def test_handle_triggers_tracker_recomputation(self) -> None:
        """录入成交后触发 ManualTracker 重新聚合持仓并持久化."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        service.get_intent.return_value = _make_intent_record()
        service.list_fills.return_value = []

        # tracker 返回一个持仓快照
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
            trade_service=service,
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

        # 验证 tracker 使用正确的参数调用
        tracker.compute_positions.assert_called_once()
        call_kwargs = tracker.compute_positions.call_args
        assert call_kwargs[1]["strategy_id"] == "strat-alpha"
        assert call_kwargs[1]["snapshot_date"] == "2026-04-11"

        # 验证持仓被持久化
        service.save_position.assert_called_once()
        saved_pos = service.save_position.call_args[0][0]
        assert saved_pos.snapshot_id == "snap-001"
        assert saved_pos.quantity == 1000

    def test_handle_computes_settlement_date(self) -> None:
        """handler 调用 compute_settlement_date 并将结果传入 DTO."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        service.get_intent.return_value = _make_intent_record()
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(
            trade_service=service,
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

        # 验证调用了 compute_settlement_date 并传入 trade_date
        tracker.compute_settlement_date.assert_called_once_with("2026-04-11")

        # 验证返回 DTO 的 settlement_date 正确
        assert result.settlement_date == "2026-04-14"

        # 验证持久化的 record 也包含 settlement_date
        saved_record = service.save_fill.call_args[0][0]
        assert saved_record.settlement_date == "2026-04-14"

    def test_handle_settlement_date_fallback(self) -> None:
        """tracker 返回空日历时 settlement_date fallback 到 trade_date."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        service.get_intent.return_value = _make_intent_record()
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        # 空日历 → compute_settlement_date 返回 trade_date 本身
        tracker.compute_settlement_date.return_value = "2026-04-11"

        handler = RecordFillHandler(
            trade_service=service,
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

        # fallback: settlement_date 等于 trade_date
        assert result.settlement_date == "2026-04-11"

        saved_record = service.save_fill.call_args[0][0]
        assert saved_record.settlement_date == "2026-04-11"


# ---------------------------------------------------------------------------
# UpdateIntentStatusHandler
# ---------------------------------------------------------------------------


class TestUpdateIntentStatusHandler:
    """UpdateIntentStatusHandler — 更新交易意图状态."""

    def test_handle_updates_status(self) -> None:
        """成功更新意图状态."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record()

        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="cancelled",
        )

        result = handler.handle(cmd)

        assert result is True
        service.update_intent_status.assert_called_once_with(
            "intent-001",
            "cancelled",
        )

    def test_handle_raises_on_missing_intent(self) -> None:
        """intent 不存在 → ValueError."""

        service = _make_trade_service()
        service.get_intent.return_value = None

        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-missing",
            status="cancelled",
        )

        with pytest.raises(ValueError, match="Intent not found: intent-missing"):
            handler.handle(cmd)

        service.update_intent_status.assert_not_called()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestTradeCommandProtocolConformance:
    """所有 Trade Handler 满足 CommandHandler Protocol."""

    def test_record_fill_handler_satisfies_protocol(self) -> None:
        service = _make_trade_service()
        tracker = _make_manual_tracker()
        handler = RecordFillHandler(
            trade_service=service,
            manual_tracker=tracker,
        )
        assert isinstance(handler, CommandHandler)

    def test_update_intent_status_handler_satisfies_protocol(self) -> None:
        service = _make_trade_service()
        handler = UpdateIntentStatusHandler(trade_service=service)
        assert isinstance(handler, CommandHandler)


# ---------------------------------------------------------------------------
# Identity validation (T28)
# ---------------------------------------------------------------------------


class TestRecordFillIdentityValidation:
    """RecordFillHandler — 身份校验 (strategy_id / instrument_id / direction)."""

    def _make_handler(self):
        """构建 handler (不导入在类外, 避免顶层导入)."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()
        service.get_intent.return_value = _make_intent_record()
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"
        return RecordFillHandler(trade_service=service, manual_tracker=tracker)

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

        with pytest.raises(ValueError, match="Strategy mismatch"):
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

        with pytest.raises(ValueError, match="Instrument mismatch"):
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

        with pytest.raises(ValueError, match="Direction mismatch"):
            handler.handle(cmd)


# ---------------------------------------------------------------------------
# Partial fill detection (T28)
# ---------------------------------------------------------------------------


class TestRecordFillPartialFillDetection:
    """RecordFillHandler — 部分成交判断."""

    def test_fill_quantity_equals_intent_returns_filled(self) -> None:
        """fill_quantity == intent_quantity → 状态更新为 filled."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        service.get_intent.return_value = intent
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(trade_service=service, manual_tracker=tracker)
        cmd = RecordFillCommand(
            fill_id="fill-full",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1000,  # == intent quantity
            fill_price=4.15,
        )
        handler.handle(cmd)

        service.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
        )

    def test_fill_quantity_less_than_intent_returns_partial(self) -> None:
        """fill_quantity < intent_quantity → 状态更新为 partially_filled."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        service.get_intent.return_value = intent
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(trade_service=service, manual_tracker=tracker)
        cmd = RecordFillCommand(
            fill_id="fill-partial",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=500,  # < intent quantity (1000)
            fill_price=4.15,
        )
        handler.handle(cmd)

        service.update_intent_status.assert_called_once_with(
            "intent-001",
            "partially_filled",
        )

    def test_fill_quantity_exceeds_intent_returns_filled(self) -> None:
        """fill_quantity > intent_quantity → 仍更新为 filled（超额成交）."""

        service = _make_trade_service()
        tracker = _make_manual_tracker()

        intent = _make_intent_record(quantity=1000)
        service.get_intent.return_value = intent
        service.list_fills.return_value = []
        tracker.compute_positions.return_value = []
        tracker.compute_settlement_date.return_value = "2026-04-14"

        handler = RecordFillHandler(trade_service=service, manual_tracker=tracker)
        cmd = RecordFillCommand(
            fill_id="fill-over",
            intent_id="intent-001",
            strategy_id="strat-alpha",
            trade_date="2026-04-11",
            instrument_id=510050,
            direction="buy",
            quantity=1500,  # > intent quantity (1000)
            fill_price=4.15,
        )
        handler.handle(cmd)

        service.update_intent_status.assert_called_once_with(
            "intent-001",
            "filled",
        )

    def test_fill_on_terminal_intent_rejected(self) -> None:
        """intent 状态为 filled/cancelled/expired 时，拒绝录入成交."""

        for terminal_status in ("filled", "cancelled", "expired"):
            service = _make_trade_service()
            tracker = _make_manual_tracker()

            intent = _make_intent_record(status=terminal_status)
            service.get_intent.return_value = intent
            tracker.compute_settlement_date.return_value = "2026-04-14"

            handler = RecordFillHandler(trade_service=service, manual_tracker=tracker)
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
                ValueError, match="expected 'pending' or 'partially_filled'"
            ):
                handler.handle(cmd)

            # 验证无副作用
            service.save_fill.assert_not_called()
            service.update_intent_status.assert_not_called()


# ---------------------------------------------------------------------------
# Status transition matrix validation (T28)
# ---------------------------------------------------------------------------


class TestUpdateIntentStatusTransitions:
    """UpdateIntentStatusHandler — 状态转换矩阵校验."""

    def test_valid_transition_pending_to_cancelled(self) -> None:
        """pending → cancelled 合法."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="cancelled")

        assert handler.handle(cmd) is True

    def test_valid_transition_pending_to_filled(self) -> None:
        """pending → filled 合法."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        assert handler.handle(cmd) is True

    def test_valid_transition_partially_filled_to_filled(self) -> None:
        """partially_filled → filled 合法."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(
            status="partially_filled",
        )
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        assert handler.handle(cmd) is True

    def test_invalid_transition_filled_to_pending_rejected(self) -> None:
        """filled → pending 非法 (终态不可回退)."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="filled")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="pending")

        with pytest.raises(ValueError, match=r"Invalid transition.*filled.*pending"):
            handler.handle(cmd)

    def test_invalid_transition_cancelled_to_filled_rejected(self) -> None:
        """cancelled → filled 非法."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="cancelled")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="filled")

        with pytest.raises(ValueError, match="Invalid transition"):
            handler.handle(cmd)

    def test_invalid_transition_expired_to_partially_filled_rejected(self) -> None:
        """expired → partially_filled 非法."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="expired")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="partially_filled",
        )

        with pytest.raises(ValueError, match="Invalid transition"):
            handler.handle(cmd)

    def test_same_status_idempotent(self) -> None:
        """相同状态 idempotent: pending → pending 不报错."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(intent_id="intent-001", status="pending")

        assert handler.handle(cmd) is True

    def test_invalid_status_name_rejected(self) -> None:
        """非法状态名称 → ValueError."""

        service = _make_trade_service()
        service.get_intent.return_value = _make_intent_record(status="pending")
        handler = UpdateIntentStatusHandler(trade_service=service)
        cmd = UpdateIntentStatusCommand(
            intent_id="intent-001",
            status="invalid_status",
        )

        with pytest.raises(ValueError, match="Invalid status"):
            handler.handle(cmd)

        service.update_intent_status.assert_not_called()
