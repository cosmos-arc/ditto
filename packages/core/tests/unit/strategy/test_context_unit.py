"""Tests for StrategyContext and DecisionStage Protocol."""


class TestStrategyContext:
    def test_create_context(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext()
        assert ctx.risk_locked_instruments == {}

    def test_lock_and_unlock(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument(1, "max_drawdown")
        assert ctx.is_locked(1)
        assert not ctx.is_locked(2)
        assert ctx.risk_locked_instruments[1] == ("max_drawdown", None)

    def test_clear_locks(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument(1, "max_drawdown")
        ctx.lock_instrument(2, "single_loss_limit")
        ctx.clear_locks("2026-01-15")
        assert ctx.risk_locked_instruments == {}

    def test_lock_instrument_overwrite(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument(1, "max_drawdown")
        ctx.lock_instrument(1, "single_loss_limit")  # 覆盖
        assert ctx.risk_locked_instruments[1] == ("single_loss_limit", None)


class TestStrategyContextPositions:
    def test_create_with_positions(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext(
            positions={1: 0.85, 2: 4.20},
        )
        assert ctx.positions == {1: 0.85, 2: 4.20}

    def test_default_empty_positions(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext()
        assert ctx.positions == {}

    def test_positions_not_cleared_by_clear_locks(self) -> None:
        from ditto_engine.strategy.context import StrategyContext

        ctx = StrategyContext(
            risk_locked_instruments={1: ("max_drawdown", None)},
            positions={1: 0.85, 2: 4.20},
        )
        ctx.clear_locks("2026-01-15")
        assert ctx.risk_locked_instruments == {}
        assert ctx.positions == {1: 0.85, 2: 4.20}


class TestDecisionStageProtocol:
    def test_protocol_is_defined(self) -> None:
        from ditto_engine.strategy.protocols import DecisionStage

        # Protocol 存在且有 process 方法签名
        assert hasattr(DecisionStage, "process")

    def test_concrete_stage_implements_protocol(self) -> None:
        import polars as pl
        from ditto_engine.strategy.context import StrategyContext

        class DummyStage:
            def process(
                self,
                frame: pl.DataFrame,
                context: StrategyContext,
            ) -> pl.DataFrame:
                return frame

        DummyStage()
