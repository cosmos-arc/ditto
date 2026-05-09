"""Tests for StrategyContextSnapshot — 策略上下文快照与恢复."""

from dataclasses import FrozenInstanceError

from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext, StrategyContextSnapshot


class TestToSnapshotCapturesState:
    """to_snapshot() 捕获当前上下文的锁和持仓。"""

    def test_to_snapshot_captures_locks_and_positions(self) -> None:
        instrument_a = InstrumentId(1)
        instrument_b = InstrumentId(2)
        ctx = StrategyContext(
            risk_locked_instruments={
                instrument_a: ("max_drawdown", "2026-06-01"),
                instrument_b: ("single_loss_limit", None),
            },
            positions={instrument_a: 0.85, instrument_b: 4.20},
        )

        snapshot = ctx.to_snapshot()

        assert snapshot.risk_locked_instruments == {
            instrument_a: ("max_drawdown", "2026-06-01"),
            instrument_b: ("single_loss_limit", None),
        }
        assert snapshot.positions == {instrument_a: 0.85, instrument_b: 4.20}

    def test_to_snapshot_empty_context(self) -> None:
        ctx = StrategyContext()
        snapshot = ctx.to_snapshot()

        assert snapshot.risk_locked_instruments == {}
        assert snapshot.positions == {}


class TestFromSnapshotRestoresContext:
    """from_snapshot() 从快照恢复上下文。"""

    def test_from_snapshot_restores_context(self) -> None:
        instrument_a = InstrumentId(1)
        snapshot = StrategyContextSnapshot(
            risk_locked_instruments={
                instrument_a: ("max_drawdown", "2026-06-01"),
            },
            positions={instrument_a: 0.85},
        )

        ctx = StrategyContext.from_snapshot(snapshot)

        assert ctx.risk_locked_instruments == {
            instrument_a: ("max_drawdown", "2026-06-01"),
        }
        assert ctx.positions == {instrument_a: 0.85}


class TestSnapshotIsFrozen:
    """StrategyContextSnapshot 是不可变的 frozen dataclass。"""

    def test_snapshot_is_frozen(self) -> None:
        snapshot = StrategyContextSnapshot(
            risk_locked_instruments={},
            positions={},
        )

        try:
            snapshot.risk_locked_instruments = {1: ("reason", None)}  # type: ignore[misc]
        except FrozenInstanceError:
            pass  # 预期：frozen dataclass 不允许赋值
        else:
            msg = "FrozenInstanceError 应在修改 snapshot 属性时抛出"
            raise AssertionError(msg)


class TestRoundtripPreservesState:
    """context → snapshot → new context → snapshot：快照内容一致。"""

    def test_roundtrip_preserves_state(self) -> None:
        instrument_a = InstrumentId(1)
        ctx = StrategyContext(
            risk_locked_instruments={
                instrument_a: ("max_drawdown", "2026-06-01"),
            },
            positions={instrument_a: 0.85},
        )

        snapshot_1 = ctx.to_snapshot()
        restored = StrategyContext.from_snapshot(snapshot_1)
        snapshot_2 = restored.to_snapshot()

        assert snapshot_1.risk_locked_instruments == snapshot_2.risk_locked_instruments
        assert snapshot_1.positions == snapshot_2.positions


class TestFromSnapshotIndependentCopy:
    """快照与原上下文互不干扰（深拷贝语义）。"""

    def test_from_snapshot_independent_copy(self) -> None:
        instrument_a = InstrumentId(1)
        instrument_b = InstrumentId(2)
        ctx = StrategyContext(
            risk_locked_instruments={
                instrument_a: ("max_drawdown", "2026-06-01"),
            },
            positions={instrument_a: 0.85},
        )

        snapshot = ctx.to_snapshot()

        # 修改原上下文
        ctx.lock_instrument(instrument_b, "single_loss_limit")
        ctx.positions[instrument_b] = 4.20

        # 快照不受影响
        assert instrument_b not in snapshot.risk_locked_instruments
        assert instrument_b not in snapshot.positions

        # 从快照恢复的上下文不受原上下文修改影响
        restored = StrategyContext.from_snapshot(snapshot)
        assert instrument_b not in restored.risk_locked_instruments
        assert instrument_b not in restored.positions
