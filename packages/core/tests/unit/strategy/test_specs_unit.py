"""Tests for StrategySpec and related types."""

from dataclasses import FrozenInstanceError

import pytest


class TestParamConstraint:
    def test_create_int_param(self) -> None:
        from ditto_engine.strategy.specs import ParamConstraint

        param = ParamConstraint(
            name="lookback",
            dtype="int",
            min_value=10,
            max_value=500,
            step=10,
        )
        assert param.dtype == "int"
        assert param.min_value == 10
        assert param.step == 10

    def test_create_enum_param(self) -> None:
        from ditto_engine.strategy.specs import ParamConstraint

        param = ParamConstraint(
            name="method",
            dtype="str",
            allowed_values=("equal_weight", "score_weight", "risk_parity"),
        )
        assert param.allowed_values == ("equal_weight", "score_weight", "risk_parity")

    def test_is_frozen(self) -> None:
        from ditto_engine.strategy.specs import ParamConstraint

        param = ParamConstraint(name="k", dtype="int", min_value=1, max_value=10)
        with pytest.raises(FrozenInstanceError):
            param.max_value = 100  # type: ignore[misc]


class TestExecutionSpec:
    def test_create_calendar_trigger(self) -> None:
        from ditto_engine.strategy.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        assert spec.frequency == "M"
        assert spec.method == "calendar"

    def test_create_with_cost_model(self) -> None:
        from ditto_engine.strategy.specs import CostModelSpec, ExecutionSpec

        spec = ExecutionSpec(
            frequency="W",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0003,
                slippage_bps=5.0,
            ),
        )
        assert spec.cost_model.commission_rate == 0.0003
        assert spec.cost_model.slippage_bps == 5.0

    def test_is_frozen(self) -> None:
        from ditto_engine.strategy.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        with pytest.raises(FrozenInstanceError):
            spec.frequency = "W"  # type: ignore[misc]


class TestConstraintSpec:
    def test_create_max_weight(self) -> None:
        from ditto_engine.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_weight_per_instrument",
            params={"value": 0.40},
            priority=1,
        )
        assert constraint.priority == 1

    def test_create_max_turnover(self) -> None:
        from ditto_engine.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_turnover",
            params={"value": 0.50},
            priority=2,
        )
        assert constraint.priority == 2

    def test_default_priority(self) -> None:
        from ditto_engine.strategy.specs import ConstraintSpec

        constraint = ConstraintSpec(type="max_drawdown", params={"value": 0.15})
        assert constraint.priority == 100  # 默认低优先级


class TestScorerSpec:
    def test_create_builtin_scorer(self) -> None:
        from ditto_engine.strategy.specs import ScorerSpec

        spec = ScorerSpec(method="rank_then_combine")
        assert spec.method == "rank_then_combine"

    def test_create_with_weights(self) -> None:
        from ditto_engine.strategy.specs import ScorerSpec

        spec = ScorerSpec(
            method="rank_then_combine",
            params={"signal_weights": {"momentum": 0.5, "cheapness": 0.3}},
        )
        assert spec.params["signal_weights"]["momentum"] == 0.5


class TestSelectorSpec:
    def test_create_top_k(self) -> None:
        from ditto_engine.strategy.specs import SelectorSpec

        spec = SelectorSpec(method="top_k", params={"k": 5, "min_count": 1})
        assert spec.method == "top_k"


class TestStrategySpec:
    def test_create_minimal_spec(self) -> None:
        from ditto_engine.strategy.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="etf_momentum_rotation",
            name="ETF Momentum Rotation",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        assert spec.strategy_id == "etf_momentum_rotation"
        assert spec.template == "etf_rotation"

    def test_create_full_spec(self) -> None:
        from ditto_engine.strategy.specs import (
            ConstraintSpec,
            CostModelSpec,
            ExecutionSpec,
            ScorerSpec,
            SelectorSpec,
            StrategySpec,
        )

        spec = StrategySpec(
            strategy_id="etf_momentum_rotation",
            name="ETF Momentum Rotation",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            scorer=ScorerSpec(method="rank_then_combine"),
            selector=SelectorSpec(method="top_k", params={"k": 5}),
            execution=ExecutionSpec(
                frequency="M",
                method="calendar",
                cost_model=CostModelSpec(commission_rate=0.0003, slippage_bps=5.0),
            ),
            constraints=[
                ConstraintSpec(
                    type="max_weight_per_instrument", params={"value": 0.40}, priority=1
                ),
                ConstraintSpec(type="max_turnover", params={"value": 0.50}, priority=2),
            ],
            benchmark="000300.SH",
            params={"lookback": 252, "vol_window": 60},
            param_constraints=[],
            tags=("momentum", "rotation", "etf"),
        )
        assert len(spec.constraints) == 2
        assert spec.tags == ("momentum", "rotation", "etf")

    def test_is_frozen(self) -> None:
        from ditto_engine.strategy.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "Changed"  # type: ignore[misc]
