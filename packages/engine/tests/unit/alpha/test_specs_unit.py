"""Tests for StrategySpec and related types."""

from dataclasses import FrozenInstanceError

import pytest


class TestParamConstraint:
    def test_create_int_param(self) -> None:
        from ditto_engine.alpha.specs import ParamConstraint

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
        from ditto_engine.alpha.specs import ParamConstraint

        param = ParamConstraint(
            name="method",
            dtype="str",
            allowed_values=("equal_weight", "score_weight", "risk_parity"),
        )
        assert param.allowed_values == ("equal_weight", "score_weight", "risk_parity")

    def test_is_frozen(self) -> None:
        from ditto_engine.alpha.specs import ParamConstraint

        param = ParamConstraint(name="k", dtype="int", min_value=1, max_value=10)
        with pytest.raises(FrozenInstanceError):
            param.max_value = 100  # type: ignore[misc]


class TestExecutionSpec:
    def test_create_calendar_trigger(self) -> None:
        from ditto_engine.alpha.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        assert spec.frequency == "M"
        assert spec.method == "calendar"

    def test_create_with_cost_model(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec

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
        from ditto_engine.alpha.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        with pytest.raises(FrozenInstanceError):
            spec.frequency = "W"  # type: ignore[misc]


class TestConstraintSpec:
    def test_create_max_weight(self) -> None:
        from ditto_engine.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_weight_per_instrument",
            params={"value": 0.40},
            priority=1,
        )
        assert constraint.priority == 1

    def test_create_max_turnover(self) -> None:
        from ditto_engine.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_turnover",
            params={"value": 0.50},
            priority=2,
        )
        assert constraint.priority == 2

    def test_default_priority(self) -> None:
        from ditto_engine.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(type="max_drawdown", params={"value": 0.15})
        assert constraint.priority == 100  # 默认低优先级


class TestScorerSpec:
    def test_create_builtin_scorer(self) -> None:
        from ditto_engine.alpha.specs import ScorerSpec

        spec = ScorerSpec(method="rank_then_combine")
        assert spec.method == "rank_then_combine"

    def test_create_with_weights(self) -> None:
        from ditto_engine.alpha.specs import ScorerSpec

        spec = ScorerSpec(
            method="rank_then_combine",
            params={"signal_weights": {"momentum": 0.5, "cheapness": 0.3}},
        )
        assert spec.params["signal_weights"]["momentum"] == 0.5


class TestSelectorSpec:
    def test_create_top_k(self) -> None:
        from ditto_engine.alpha.specs import SelectorSpec

        spec = SelectorSpec(method="top_k", params={"k": 5, "min_count": 1})
        assert spec.method == "top_k"


class TestStrategySpec:
    def test_create_minimal_spec(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

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
        from ditto_engine.alpha.specs import (
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
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "Changed"  # type: ignore[misc]


class TestStrategySpecValidation:
    """F0.4: StrategySpec.__post_init__ 参数校验测试."""

    # -- 必填字段非空 --

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("strategy_id", ""),
            ("name", ""),
            ("template", ""),
            ("universe", ""),
            ("asset_class", ""),
        ],
    )
    def test_required_field_non_empty(self, field_name: str, value: str) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        with pytest.raises(ValueError, match="must be non-empty"):
            StrategySpec(
                strategy_id=value if field_name == "strategy_id" else "id",
                name=value if field_name == "name" else "Name",
                template=value if field_name == "template" else "etf_rotation",
                universe=value if field_name == "universe" else "csi_etf_broad",
                asset_class=value if field_name == "asset_class" else "etf",
            )

    # -- template 枚举值 --

    def test_template_valid_values(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        valid_templates = (
            "etf_rotation",
            "etf_trend_swing",
            "stock_selection",
            "stock_sector_rotation",
        )
        for tpl in valid_templates:
            spec = StrategySpec(
                strategy_id="id",
                name="N",
                template=tpl,
                universe="u",
                asset_class="etf",
            )
            assert spec.template == tpl

    def test_template_invalid_raises(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        with pytest.raises(ValueError, match="template"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="bad_template",
                universe="u",
                asset_class="etf",
            )

    # -- benchmark 格式 --

    def test_benchmark_none_ok(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            benchmark=None,
        )
        assert spec.benchmark is None

    def test_benchmark_valid_format(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        for code in ("000300.SH", "399006.SZ", "510300.SH"):
            spec = StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                benchmark=code,
            )
            assert spec.benchmark == code

    def test_benchmark_invalid_format_raises(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        for bad in ("INVALID", "000300", "000300.SH.SZ", "SH000300"):
            with pytest.raises(ValueError, match="benchmark"):
                StrategySpec(
                    strategy_id="id",
                    name="N",
                    template="etf_rotation",
                    universe="u",
                    asset_class="etf",
                    benchmark=bad,
                )

    # -- execution.frequency 枚举值 --

    @pytest.mark.parametrize("freq", ["D", "W", "M", "Q"])
    def test_execution_frequency_valid(self, freq: str) -> None:
        from ditto_engine.alpha.specs import ExecutionSpec, StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            execution=ExecutionSpec(frequency=freq),
        )
        assert spec.execution.frequency == freq

    def test_execution_frequency_invalid_raises(self) -> None:
        from ditto_engine.alpha.specs import ExecutionSpec, StrategySpec

        with pytest.raises(ValueError, match="frequency"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                execution=ExecutionSpec(frequency="Y"),
            )

    # -- cost_model 边界 --

    def test_commission_rate_negative_raises(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec, StrategySpec

        with pytest.raises(ValueError, match="commission_rate"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                execution=ExecutionSpec(
                    cost_model=CostModelSpec(commission_rate=-0.01),
                ),
            )

    def test_commission_rate_exceeds_one_raises(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec, StrategySpec

        with pytest.raises(ValueError, match="commission_rate"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                execution=ExecutionSpec(
                    cost_model=CostModelSpec(commission_rate=1.5),
                ),
            )

    def test_commission_rate_zero_and_one_ok(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec, StrategySpec

        for rate in (0.0, 1.0):
            spec = StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                execution=ExecutionSpec(cost_model=CostModelSpec(commission_rate=rate)),
            )
            assert spec.execution.cost_model.commission_rate == rate

    def test_slippage_bps_negative_raises(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec, StrategySpec

        with pytest.raises(ValueError, match="slippage_bps"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                execution=ExecutionSpec(
                    cost_model=CostModelSpec(slippage_bps=-1.0),
                ),
            )

    def test_slippage_bps_zero_ok(self) -> None:
        from ditto_engine.alpha.specs import CostModelSpec, ExecutionSpec, StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            execution=ExecutionSpec(cost_model=CostModelSpec(slippage_bps=0.0)),
        )
        assert spec.execution.cost_model.slippage_bps == 0.0

    # -- signal_expressions / signal_weights 一致性 --

    def test_signal_weights_mismatch_raises(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        with pytest.raises(ValueError, match="signal_weights"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="etf_rotation",
                universe="u",
                asset_class="etf",
                signal_expressions=("expr1", "expr2"),
                signal_weights=(0.5,),
            )

    def test_signal_weights_matching_ok(self) -> None:
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            signal_expressions=("expr1", "expr2"),
            signal_weights=(0.6, 0.4),
        )
        assert len(spec.signal_expressions) == len(spec.signal_weights)
