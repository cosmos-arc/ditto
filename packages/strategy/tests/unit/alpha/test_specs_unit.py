"""Tests for StrategySpec and related types."""

import operator
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError

import pytest
from ditto_strategy.errors import StrategySpecError


class TestParamConstraint:
    def test_create_int_param(self) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

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

    @pytest.mark.parametrize(
        "numeric_values",
        [
            pytest.param((10, 20, 5), id="integer-inputs"),
            pytest.param((10.0, 20.0, 5.0), id="float-inputs"),
        ],
    )
    def test_normalizes_numeric_identity_fields_to_floats(
        self,
        numeric_values: tuple[int | float, int | float, int | float],
    ) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        minimum, maximum, step = numeric_values
        param = ParamConstraint(
            name="lookback",
            dtype="int",
            min_value=minimum,
            max_value=maximum,
            step=step,
        )

        assert param.min_value == 10.0
        assert param.max_value == 20.0
        assert param.step == 5.0
        assert type(param.min_value) is float
        assert type(param.max_value) is float
        assert type(param.step) is float

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_accepts_exact_float_integer_boundary_and_rejects_lossy_integer(
        self,
        field_name: str,
    ) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        constructor: Callable[..., ParamConstraint] = ParamConstraint
        exact_integer = 2**53
        lossy_integer = exact_integer + 1
        assert float(exact_integer) == float(lossy_integer)

        exact = constructor(
            name="lookback",
            dtype="int",
            **{field_name: exact_integer},
        )
        exact_value = getattr(exact, field_name)
        assert exact_value == float(exact_integer)
        assert type(exact_value) is float

        with pytest.raises(StrategySpecError) as exc_info:
            constructor(
                name="lookback",
                dtype="int",
                **{field_name: lossy_integer},
            )

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == "non_finite_parameter_identity"

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_rejects_bool_numeric_identity_fields(self, field_name: str) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        constructor: Callable[..., ParamConstraint] = ParamConstraint

        with pytest.raises(StrategySpecError) as exc_info:
            constructor(
                name="lookback",
                dtype="int",
                **{field_name: True},
            )

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == "non_finite_parameter_identity"

    def test_create_enum_param(self) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        param = ParamConstraint(
            name="method",
            dtype="str",
            allowed_values=("equal_weight", "score_weight", "risk_parity"),
        )
        assert param.allowed_values == ("equal_weight", "score_weight", "risk_parity")

    def test_is_frozen(self) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        param = ParamConstraint(name="k", dtype="int", min_value=1, max_value=10)
        with pytest.raises(FrozenInstanceError):
            param.max_value = 100  # type: ignore[misc]

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="positive-infinity"),
            pytest.param(float("-inf"), id="negative-infinity"),
        ],
    )
    def test_rejects_non_finite_numeric_identity_fields(
        self,
        field_name: str,
        invalid_value: float,
    ) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        with pytest.raises(StrategySpecError, match=field_name):
            ParamConstraint(
                name="lookback",
                dtype="float",
                **{field_name: invalid_value},
            )

    @pytest.mark.parametrize(
        ("field_name", "invalid_value", "expected_reason"),
        [
            pytest.param("name", "", "invalid_parameter_name", id="empty-name"),
            pytest.param("name", True, "invalid_parameter_name", id="bool-name"),
            pytest.param("name", None, "invalid_parameter_name", id="null-name"),
            pytest.param("dtype", True, "invalid_parameter_dtype", id="bool-dtype"),
            pytest.param(
                "dtype",
                "decimal",
                "invalid_parameter_dtype",
                id="unsupported-dtype",
            ),
            pytest.param(
                "allowed_values",
                "equal_weight",
                "invalid_parameter_allowed_values",
                id="string-is-not-container",
            ),
            pytest.param(
                "allowed_values",
                None,
                "invalid_parameter_allowed_values",
                id="null-allowed-values",
            ),
            pytest.param(
                "allowed_values",
                ("equal_weight", True),
                "invalid_parameter_allowed_values",
                id="bool-allowed-value",
            ),
        ],
    )
    def test_rejects_invalid_canonical_identity_shapes(
        self,
        field_name: str,
        invalid_value: object,
        expected_reason: str,
    ) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        constructor: Callable[..., ParamConstraint] = ParamConstraint
        values: dict[str, object] = {
            "name": "allocation_method",
            "dtype": "str",
            "allowed_values": ("equal_weight",),
        }
        values[field_name] = invalid_value

        with pytest.raises(StrategySpecError) as exc_info:
            constructor(**values)

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == expected_reason

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_huge_integer_identity_raises_typed_spec_error(
        self,
        field_name: str,
    ) -> None:
        from ditto_strategy.alpha.specs import ParamConstraint

        constructor: Callable[..., ParamConstraint] = ParamConstraint

        with pytest.raises(StrategySpecError) as exc_info:
            constructor(
                name="lookback",
                dtype="int",
                **{field_name: 10**1000},
            )

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == "non_finite_parameter_identity"


class TestExecutionSpec:
    def test_create_calendar_trigger(self) -> None:
        from ditto_strategy.alpha.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        assert spec.frequency == "M"
        assert spec.method == "calendar"

    def test_create_with_cost_model(self) -> None:
        from ditto_strategy.alpha.specs import CostModelSpec, ExecutionSpec

        spec = ExecutionSpec(
            frequency="W",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0003,
                slippage_bps=3.0,
            ),
        )
        assert spec.cost_model.commission_rate == 0.0003
        assert spec.cost_model.slippage_bps == 3.0

    def test_cost_model_default_slippage_is_1_bps(self) -> None:
        from ditto_strategy.alpha.specs import CostModelSpec

        spec = CostModelSpec()
        assert spec.slippage_bps == 1.0

    def test_is_frozen(self) -> None:
        from ditto_strategy.alpha.specs import ExecutionSpec

        spec = ExecutionSpec(frequency="M", method="calendar")
        with pytest.raises(FrozenInstanceError):
            spec.frequency = "W"  # type: ignore[misc]


class TestConstraintSpec:
    def test_create_max_weight(self) -> None:
        from ditto_strategy.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_weight_per_instrument",
            params={"value": 0.40},
            priority=1,
        )
        assert constraint.priority == 1

    def test_create_max_turnover(self) -> None:
        from ditto_strategy.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(
            type="max_turnover",
            params={"value": 0.50},
            priority=2,
        )
        assert constraint.priority == 2

    def test_default_priority(self) -> None:
        from ditto_strategy.alpha.specs import ConstraintSpec

        constraint = ConstraintSpec(type="max_drawdown", params={"value": 0.15})
        assert constraint.priority == 100  # 默认低优先级


class TestScorerSpec:
    def test_create_builtin_scorer(self) -> None:
        from ditto_strategy.alpha.specs import ScorerSpec

        spec = ScorerSpec(method="rank_then_combine")
        assert spec.method == "rank_then_combine"

    def test_create_with_weights(self) -> None:
        from ditto_strategy.alpha.specs import ScorerSpec

        spec = ScorerSpec(
            method="rank_then_combine",
            params={"signal_weights": {"momentum": 0.5, "cheapness": 0.3}},
        )
        assert spec.params["signal_weights"]["momentum"] == 0.5


class TestSelectorSpec:
    def test_create_top_k(self) -> None:
        from ditto_strategy.alpha.specs import SelectorSpec

        spec = SelectorSpec(method="top_k", params={"k": 5, "min_count": 1})
        assert spec.method == "top_k"


class TestStrategySpec:
    def test_create_minimal_spec(self) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

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
        from ditto_strategy.alpha.specs import (
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
        from ditto_strategy.alpha.specs import StrategySpec

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
        from ditto_strategy.alpha.specs import StrategySpec

        with pytest.raises(StrategySpecError, match="must be non-empty"):
            StrategySpec(
                strategy_id=value if field_name == "strategy_id" else "id",
                name=value if field_name == "name" else "Name",
                template=value if field_name == "template" else "etf_rotation",
                universe=value if field_name == "universe" else "csi_etf_broad",
                asset_class=value if field_name == "asset_class" else "etf",
            )

    # -- template 枚举值 --

    def test_template_valid_values(self) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

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
        from ditto_strategy.alpha.specs import StrategySpec

        with pytest.raises(StrategySpecError, match="template"):
            StrategySpec(
                strategy_id="id",
                name="N",
                template="bad_template",
                universe="u",
                asset_class="etf",
            )

    # -- benchmark 格式 --

    def test_benchmark_none_ok(self) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            benchmark=None,
        )
        assert spec.benchmark is None

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param("000300.SH", id="hs300"),
            pytest.param("000905.SH", id="zz500"),
            pytest.param("000852.SH", id="zz1000"),
            pytest.param("000016.SH", id="sz50"),
            pytest.param("399006.SZ", id="cyb"),
            pytest.param("399673.SZ", id="cyb50"),
            pytest.param("000688.SH", id="kc50"),
            pytest.param("000001.SH", id="sz"),
            pytest.param("399001.SZ", id="szcz"),
        ],
    )
    def test_benchmark_known_index_ok(self, code: str) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="id",
            name="N",
            template="etf_rotation",
            universe="u",
            asset_class="etf",
            benchmark=code,
        )
        assert spec.benchmark == code

    @pytest.mark.parametrize(
        "code",
        [
            pytest.param("999999.SH", id="valid-format-unknown-index"),
            pytest.param("888888.SZ", id="valid-format-unknown-index-2"),
            pytest.param("510300.SH", id="etf-valid-format"),
        ],
    )
    def test_benchmark_valid_format_passes(self, code: str) -> None:
        """格式合法（NNNNNN.SH|SZ）的 benchmark 均通过验证，不再限于已知指数."""
        from ditto_strategy.alpha.specs import StrategySpec

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
        from ditto_strategy.alpha.specs import StrategySpec

        for bad in ("INVALID", "000300", "000300.SH.SZ", "SH000300"):
            with pytest.raises(StrategySpecError, match="benchmark"):
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
        from ditto_strategy.alpha.specs import ExecutionSpec, StrategySpec

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
        from ditto_strategy.alpha.specs import ExecutionSpec, StrategySpec

        with pytest.raises(StrategySpecError, match="frequency"):
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
        from ditto_strategy.alpha.specs import (
            CostModelSpec,
            ExecutionSpec,
            StrategySpec,
        )

        with pytest.raises(StrategySpecError, match="commission_rate"):
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
        from ditto_strategy.alpha.specs import (
            CostModelSpec,
            ExecutionSpec,
            StrategySpec,
        )

        with pytest.raises(StrategySpecError, match="commission_rate"):
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
        from ditto_strategy.alpha.specs import (
            CostModelSpec,
            ExecutionSpec,
            StrategySpec,
        )

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
        from ditto_strategy.alpha.specs import (
            CostModelSpec,
            ExecutionSpec,
            StrategySpec,
        )

        with pytest.raises(StrategySpecError, match="slippage_bps"):
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
        from ditto_strategy.alpha.specs import (
            CostModelSpec,
            ExecutionSpec,
            StrategySpec,
        )

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
        from ditto_strategy.alpha.specs import StrategySpec

        with pytest.raises(StrategySpecError, match="signal_weights"):
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
        from ditto_strategy.alpha.specs import StrategySpec

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

    def test_production_strategy_rejects_inline_nested_factor_expression(
        self,
    ) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

        with pytest.raises(StrategySpecError, match="production factor expression"):
            StrategySpec(
                strategy_id="prod-stock",
                name="Production Stock",
                template="stock_selection",
                universe="csi_300",
                asset_class="stock",
                tags=("production",),
                signal_expressions=("cs_rank(ts_mean(market.close, 20))",),
            )

    def test_production_strategy_allows_materialized_time_series_intermediate(
        self,
    ) -> None:
        from ditto_strategy.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="prod-stock",
            name="Production Stock",
            template="stock_selection",
            universe="csi_300",
            asset_class="stock",
            tags=("production",),
            signal_expressions=("cs_rank(ts_mean_close_20)",),
            params={"materialized_factor_columns": ("ts_mean_close_20",)},
        )

        assert spec.signal_expressions == ("cs_rank(ts_mean_close_20)",)


class TestStrategySpecV2:
    """V2 canonical spec 与 legacy runtime spec 保持显式类型边界。"""

    def test_is_a_distinct_frozen_type_from_legacy_strategy_spec(self) -> None:
        from ditto_strategy.alpha.nodes import (
            NodeCategory,
            NodeInstance,
            NodeRef,
            PipelineSpec,
        )
        from ditto_strategy.alpha.specs import (
            StrategyKind,
            StrategySpec,
            StrategySpecV2,
        )

        pipeline = PipelineSpec(
            nodes=(
                NodeInstance(
                    node_id="universe",
                    ref=NodeRef("builtin.universe", "1"),
                    category=NodeCategory.UNIVERSE,
                    config={"universe_id": "csi_300"},
                ),
            ),
            sequence=("universe",),
        )
        spec = StrategySpecV2(
            schema_version=2,
            strategy_family_id="stock-alpha",
            strategy_kind=StrategyKind.STOCK_SELECTION,
            name="Stock Alpha",
            pipeline=pipeline,
        )

        assert not isinstance(spec, StrategySpec)
        with pytest.raises(FrozenInstanceError):
            spec.name = "Changed"  # type: ignore[misc]

    def test_rejects_non_v2_schema_version(self) -> None:
        from ditto_strategy.alpha.nodes import PipelineSpec
        from ditto_strategy.alpha.specs import StrategyKind, StrategySpecV2

        with pytest.raises(StrategySpecError, match="schema_version"):
            StrategySpecV2(
                schema_version=1,
                strategy_family_id="stock-alpha",
                strategy_kind=StrategyKind.STOCK_SELECTION,
                name="Stock Alpha",
                pipeline=PipelineSpec(nodes=(), sequence=()),
            )

    def test_metadata_is_a_recursive_immutable_snapshot(self) -> None:
        from ditto_strategy.alpha.nodes import PipelineSpec
        from ditto_strategy.alpha.specs import StrategyKind, StrategySpecV2

        source: dict[str, object] = {"layout": {"columns": ["factor", "score"]}}
        spec = StrategySpecV2(
            schema_version=2,
            strategy_family_id="stock-alpha",
            strategy_kind=StrategyKind.STOCK_SELECTION,
            name="Stock Alpha",
            pipeline=PipelineSpec(nodes=(), sequence=()),
            parameter_schema=(),
            metadata=source,
            tags=(),
        )
        layout = spec.metadata["layout"]
        assert isinstance(layout, Mapping)
        columns = layout["columns"]
        assert isinstance(columns, tuple)

        with pytest.raises(TypeError):
            operator.setitem(spec.metadata, "added", True)
        with pytest.raises(TypeError):
            operator.setitem(layout, "added", True)
        with pytest.raises(TypeError):
            operator.setitem(columns, 0, "changed")

        source_layout = source["layout"]
        assert isinstance(source_layout, dict)
        source_layout["columns"] = ["changed"]
        assert layout["columns"] == ("factor", "score")

    @pytest.mark.parametrize(
        ("field_name", "invalid_value"),
        [
            pytest.param("parameter_schema", [], id="parameter-schema-list"),
            pytest.param("parameter_schema", None, id="parameter-schema-none"),
            pytest.param(
                "parameter_schema",
                (object(),),
                id="parameter-schema-invalid-element",
            ),
            pytest.param("tags", [], id="tags-list"),
            pytest.param("tags", None, id="tags-none"),
            pytest.param("tags", (object(),), id="tags-invalid-element"),
            pytest.param("metadata", [], id="metadata-list"),
            pytest.param("metadata", None, id="metadata-none"),
        ],
    )
    def test_programmatic_boundaries_require_canonical_container_types(
        self,
        field_name: str,
        invalid_value: object,
    ) -> None:
        from ditto_strategy.alpha.nodes import PipelineSpec
        from ditto_strategy.alpha.specs import StrategyKind, StrategySpecV2

        values: dict[str, object] = {
            "schema_version": 2,
            "strategy_family_id": "stock-alpha",
            "strategy_kind": StrategyKind.STOCK_SELECTION,
            "name": "Stock Alpha",
            "pipeline": PipelineSpec(nodes=(), sequence=()),
            "parameter_schema": (),
            "metadata": {},
            "tags": (),
        }
        values[field_name] = invalid_value
        constructor: Callable[..., StrategySpecV2] = StrategySpecV2

        with pytest.raises(StrategySpecError, match=field_name):
            constructor(**values)
