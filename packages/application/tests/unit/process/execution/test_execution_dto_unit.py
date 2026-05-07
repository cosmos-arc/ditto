"""Phase 2 领域对象单元测试 — app DTO + data Record + 跨层映射."""

from __future__ import annotations

import pytest

# ===========================================================================
# Data 层 Record 构造测试
# ===========================================================================


class TestSignalRecord:
    """SignalRecord — 交易意图持久化记录."""

    def test_construction_with_required_fields(self) -> None:
        from ditto_execution.models import SignalRecord

        record = SignalRecord(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        assert record.intent_id == "intent-1"
        assert record.instrument_id == 1
        assert record.direction == "buy"
        assert record.delta_weight == 0.2
        assert record.quantity is None
        assert record.status == "pending"
        assert record.created_at == ""

    def test_frozen_immutability(self) -> None:
        from ditto_execution.models import SignalRecord

        record = SignalRecord(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        with pytest.raises(AttributeError):
            record.status = "filled"  # type: ignore[misc]


class TestFillRecord:
    """FillRecord — 人工成交持久化记录."""

    def test_construction_with_required_fields(self) -> None:
        from ditto_execution.models import FillRecord

        record = FillRecord(
            fill_id="fill-1",
            intent_id="intent-1",
            strategy_id="strat-1",
            trade_date="2026-04-11",
            instrument_id=1,
            direction="buy",
            quantity=1000,
            fill_price=1.5,
            fee=5.0,
        )
        assert record.fill_id == "fill-1"
        assert record.quantity == 1000
        assert record.fill_price == 1.5
        assert record.fee == 5.0
        assert record.slippage == 0.0
        assert record.notes == ""
        assert record.settlement_date == ""
        assert record.created_at == ""


class TestPositionRecord:
    """PositionRecord — 实际持仓快照持久化记录."""

    def test_construction_with_required_fields(self) -> None:
        from ditto_execution.models import PositionRecord

        record = PositionRecord(
            snapshot_id="snap-1",
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=1.5,
            market_value=1500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        assert record.snapshot_id == "snap-1"
        assert record.quantity == 1000
        assert record.available_quantity == 0
        assert record.created_at == ""


# ===========================================================================
# App 层 DTO 构造测试
# ===========================================================================


class TestTradeIntent:
    """TradeIntent — 交易意图 app 层 DTO."""

    def test_construction_with_defaults(self) -> None:
        from ditto_application.execution_dto import TradeIntent

        intent = TradeIntent(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        assert intent.intent_id == "intent-1"
        assert intent.instrument_id == 1
        assert intent.quantity is None
        assert intent.status == "pending"

    def test_frozen_immutability(self) -> None:
        from ditto_application.execution_dto import TradeIntent

        intent = TradeIntent(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        with pytest.raises(AttributeError):
            intent.status = "filled"  # type: ignore[misc]


class TestManualExecutionFill:
    """ManualExecutionFill — 人工成交 app 层 DTO."""

    def test_construction_with_defaults(self) -> None:
        from ditto_application.execution_dto import ManualExecutionFill

        fill = ManualExecutionFill(
            fill_id="fill-1",
            intent_id="intent-1",
            strategy_id="strat-1",
            trade_date="2026-04-11",
            instrument_id=1,
            direction="buy",
            quantity=1000,
            fill_price=1.5,
            fee=5.0,
        )
        assert fill.fill_id == "fill-1"
        assert fill.slippage == 0.0
        assert fill.notes == ""


class TestActualPositionSnapshot:
    """ActualPositionSnapshot — 实际持仓快照 app 层 DTO."""

    def test_construction(self) -> None:
        from ditto_application.execution_dto import ActualPositionSnapshot

        snapshot = ActualPositionSnapshot(
            snapshot_id="snap-1",
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=1.5,
            market_value=1500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        assert snapshot.snapshot_id == "snap-1"
        assert snapshot.available_quantity == 0


# ===========================================================================
# 跨层映射测试
# ===========================================================================


class TestDtoRecordMapping:
    """DTO ↔ Record 跨层映射."""

    def test_intent_to_record(self) -> None:
        from ditto_application.execution_dto import TradeIntent, intent_to_record

        intent = TradeIntent(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        record = intent_to_record(intent)

        assert record.intent_id == "intent-1"
        assert record.instrument_id == 1
        assert record.direction == "buy"
        assert record.delta_weight == 0.2

    def test_fill_to_record(self) -> None:
        from ditto_application.execution_dto import (
            ManualExecutionFill,
            fill_to_record,
        )

        fill = ManualExecutionFill(
            fill_id="fill-1",
            intent_id="intent-1",
            strategy_id="strat-1",
            trade_date="2026-04-11",
            instrument_id=1,
            direction="buy",
            quantity=1000,
            fill_price=1.5,
            fee=5.0,
        )
        record = fill_to_record(fill)

        assert record.fill_id == "fill-1"
        assert record.instrument_id == 1
        assert record.quantity == 1000

    def test_snapshot_to_record(self) -> None:
        from ditto_application.execution_dto import (
            ActualPositionSnapshot,
            snapshot_to_record,
        )

        snapshot = ActualPositionSnapshot(
            snapshot_id="snap-1",
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=1.5,
            market_value=1500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        record = snapshot_to_record(snapshot)

        assert record.snapshot_id == "snap-1"
        assert record.instrument_id == 1

    def test_record_to_intent(self) -> None:
        from ditto_application.execution_dto import record_to_intent
        from ditto_execution.models import SignalRecord

        record = SignalRecord(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="buy",
            target_weight=0.3,
            current_weight=0.1,
            delta_weight=0.2,
        )
        intent = record_to_intent(record)

        assert intent.intent_id == "intent-1"
        assert intent.instrument_id == 1
        assert intent.direction == "buy"

    def test_record_to_fill(self) -> None:
        from ditto_application.execution_dto import record_to_fill
        from ditto_execution.models import FillRecord

        record = FillRecord(
            fill_id="fill-1",
            intent_id="intent-1",
            strategy_id="strat-1",
            trade_date="2026-04-11",
            instrument_id=1,
            direction="buy",
            quantity=1000,
            fill_price=1.5,
            fee=5.0,
        )
        fill = record_to_fill(record)

        assert fill.fill_id == "fill-1"
        assert fill.instrument_id == 1
        assert fill.quantity == 1000

    def test_record_to_snapshot(self) -> None:
        from ditto_application.execution_dto import record_to_snapshot
        from ditto_execution.models import PositionRecord

        record = PositionRecord(
            snapshot_id="snap-1",
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
            instrument_id=1,
            quantity=1000,
            available_quantity=0,
            average_cost=1.5,
            market_value=1500.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=5.0,
        )
        snapshot = record_to_snapshot(record)

        assert snapshot.snapshot_id == "snap-1"
        assert snapshot.instrument_id == 1

    def test_roundtrip_intent(self) -> None:
        """DTO → Record → DTO 往返映射保持一致性."""
        from ditto_application.execution_dto import (
            TradeIntent,
            intent_to_record,
            record_to_intent,
        )

        original = TradeIntent(
            intent_id="intent-1",
            strategy_id="strat-1",
            signal_date="2026-04-10",
            instrument_id=1,
            direction="sell",
            target_weight=0.0,
            current_weight=0.2,
            delta_weight=-0.2,
            quantity=500,
            status="pending",
        )
        record = intent_to_record(original)
        restored = record_to_intent(record)

        assert restored.intent_id == original.intent_id
        assert restored.instrument_id == original.instrument_id
        assert restored.direction == original.direction
        assert restored.quantity == original.quantity
        assert restored.status == original.status

    def test_roundtrip_fill(self) -> None:
        """Fill DTO → Record → DTO 往返映射保持一致性."""
        from ditto_application.execution_dto import (
            ManualExecutionFill,
            fill_to_record,
            record_to_fill,
        )

        original = ManualExecutionFill(
            fill_id="fill-1",
            intent_id="intent-1",
            strategy_id="strat-1",
            trade_date="2026-04-11",
            instrument_id=1,
            direction="sell",
            quantity=500,
            fill_price=2.0,
            fee=3.0,
            slippage=0.01,
            notes="partial fill",
        )
        record = fill_to_record(original)
        restored = record_to_fill(record)

        assert restored.fill_id == original.fill_id
        assert restored.quantity == original.quantity
        assert restored.slippage == original.slippage
        assert restored.notes == original.notes

    def test_roundtrip_snapshot(self) -> None:
        """Snapshot DTO → Record → DTO 往返映射保持一致性."""
        from ditto_application.execution_dto import (
            ActualPositionSnapshot,
            record_to_snapshot,
            snapshot_to_record,
        )

        original = ActualPositionSnapshot(
            snapshot_id="snap-1",
            strategy_id="strat-1",
            snapshot_date="2026-04-11",
            instrument_id=1,
            quantity=1000,
            available_quantity=500,
            average_cost=1.5,
            market_value=2000.0,
            unrealized_pnl=500.0,
            realized_pnl=100.0,
            total_fees=15.0,
        )
        record = snapshot_to_record(original)
        restored = record_to_snapshot(record)

        assert restored.snapshot_id == original.snapshot_id
        assert restored.quantity == original.quantity
        assert restored.unrealized_pnl == original.unrealized_pnl
        assert restored.realized_pnl == original.realized_pnl
