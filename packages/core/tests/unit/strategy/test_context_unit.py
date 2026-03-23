"""Tests for StrategyContext and DecisionStage Protocol."""


class TestStrategyContext:
    def test_create_context(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        assert ctx.risk_locked_instruments == {}

    def test_lock_and_unlock(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        assert ctx.is_locked("159915.SZ")
        assert not ctx.is_locked("510300.SH")
        assert ctx.risk_locked_instruments["159915.SZ"] == ("max_drawdown", None)

    def test_clear_locks(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        ctx.lock_instrument("510300.SH", "single_loss_limit")
        ctx.clear_locks("2026-01-15")
        assert ctx.risk_locked_instruments == {}

    def test_lock_instrument_overwrite(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        ctx.lock_instrument("159915.SZ", "max_drawdown")
        ctx.lock_instrument("159915.SZ", "single_loss_limit")  # 覆盖
        assert ctx.risk_locked_instruments["159915.SZ"] == ("single_loss_limit", None)


class TestStrategyContextPositions:
    def test_create_with_positions(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext(
            positions={"159915.SZ": 0.85, "510300.SH": 4.20},
        )
        assert ctx.positions == {"159915.SZ": 0.85, "510300.SH": 4.20}

    def test_default_empty_positions(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext()
        assert ctx.positions == {}

    def test_positions_not_cleared_by_clear_locks(self) -> None:
        from ditto_core.strategy.context import StrategyContext

        ctx = StrategyContext(
            risk_locked_instruments={"159915.SZ": ("max_drawdown", None)},
            positions={"159915.SZ": 0.85, "510300.SH": 4.20},
        )
        ctx.clear_locks("2026-01-15")
        assert ctx.risk_locked_instruments == {}
        assert ctx.positions == {"159915.SZ": 0.85, "510300.SH": 4.20}


class TestDecisionStageProtocol:
    def test_protocol_is_defined(self) -> None:
        from ditto_core.strategy.protocols import DecisionStage

        # Protocol 存在且有 process 方法签名
        assert hasattr(DecisionStage, "process")

    def test_concrete_stage_implements_protocol(self) -> None:
        import polars as pl
        from ditto_core.strategy.context import StrategyContext
        from ditto_core.strategy.protocols import DecisionStage

        class DummyStage:
            def process(
                self,
                frame: pl.DataFrame,
                context: StrategyContext,
            ) -> pl.DataFrame:
                return frame

        stage = DummyStage()
        assert isinstance(stage, DecisionStage)
