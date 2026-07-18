"""StrategySpec v2 canonical codec 与 legacy migration adapter 测试。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import orjson
import pytest
from ditto_kernel.order import OrderType
from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategyKind,
    StrategySpec,
    StrategySpecV2,
)
from ditto_strategy.errors import StrategySpecError


def _make_v2_spec(*, reversed_config: bool = False) -> StrategySpecV2:
    factor_config = (
        {"weights": {"value": 0.4, "momentum": 0.6}, "lookback": 60}
        if not reversed_config
        else {"lookback": 60, "weights": {"momentum": 0.6, "value": 0.4}}
    )
    nodes = (
        NodeInstance(
            node_id="universe",
            ref=NodeRef("builtin.universe", "1"),
            category=NodeCategory.UNIVERSE,
            config={"universe_id": "csi_a_share", "asset_class": "stock"},
        ),
        NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "2"),
            category=NodeCategory.FACTOR_SET,
            config=factor_config,
        ),
        NodeInstance(
            node_id="scorer",
            ref=NodeRef("builtin.scorer", "1"),
            category=NodeCategory.SCORER,
            config={"method": "rank_then_combine"},
        ),
    )
    return StrategySpecV2(
        schema_version=2,
        strategy_family_id="family-stock-alpha",
        strategy_kind=StrategyKind.STOCK_SELECTION,
        name="股票多因子",
        pipeline=PipelineSpec(
            nodes=nodes,
            sequence=("universe", "factors", "scorer"),
        ),
        parameter_schema=(
            ParamConstraint(
                name="pipeline.nodes.factors.config.lookback",
                dtype="int",
                min_value=20,
                max_value=120,
                step=20,
            ),
        ),
        metadata={"layout": {"x": 10, "y": 20}, "description": "UI only"},
        tags=("draft", "research"),
    )


def _make_legacy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="legacy-etf-alpha",
        name="Legacy ETF Alpha",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        scorer=ScorerSpec(method="rank_then_combine", params={"ascending": False}),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        execution=ExecutionSpec(
            frequency="W",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0003,
                slippage_bps=3.0,
            ),
            default_order_type=OrderType.MARKET,
        ),
        constraints=(
            ConstraintSpec(
                type="max_weight_per_instrument",
                params={"max_weight": 0.4},
                priority=1,
            ),
        ),
        benchmark="000300.SH",
        params={"lookback": 60, "cash_target": 0.05},
        param_constraints=(
            ParamConstraint(
                name="lookback",
                dtype="int",
                min_value=20,
                max_value=120,
                step=20,
            ),
        ),
        tags=("legacy", "ui-tag"),
        signal_expressions=("momentum_1m", "volatility_factor"),
        signal_weights=(0.7, 0.3),
        required_datasets=("etf_daily",),
    )


class TestCanonicalSpecCodec:
    """Canonical bytes 只表达完整执行语义。"""

    def test_bytes_use_recursive_canonical_key_ordering(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        canonical = canonical_spec_bytes(_make_v2_spec())
        parsed = orjson.loads(canonical)

        assert canonical == orjson.dumps(parsed, option=orjson.OPT_SORT_KEYS)

    def test_same_semantics_have_identical_bytes_and_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import (
            canonical_spec_bytes,
            canonical_spec_hash,
        )

        first = _make_v2_spec()
        second = _make_v2_spec(reversed_config=True)
        second = replace(
            second,
            pipeline=replace(
                second.pipeline,
                nodes=tuple(reversed(second.pipeline.nodes)),
            ),
        )

        assert canonical_spec_bytes(first) == canonical_spec_bytes(second)
        assert canonical_spec_hash(first) == canonical_spec_hash(second)

    def test_source_mutation_after_construction_cannot_drift_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_hash

        config: dict[str, object] = {"weights": {"momentum": [0.4, 0.6]}}
        node = NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
            config=config,
        )
        spec = StrategySpecV2(
            schema_version=2,
            strategy_family_id="family-stock-alpha",
            strategy_kind=StrategyKind.STOCK_SELECTION,
            name="Stock Alpha",
            pipeline=PipelineSpec(nodes=(node,), sequence=("factors",)),
            parameter_schema=(),
            metadata={},
            tags=(),
        )
        original_hash = canonical_spec_hash(spec)
        weights = config["weights"]
        assert isinstance(weights, dict)
        weights["momentum"] = [1.0]

        assert canonical_spec_hash(spec) == original_hash

    def test_parameter_allowed_values_snapshot_prevents_source_hash_drift(
        self,
    ) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_hash

        source = ["equal_weight", "score_weight"]
        constructor: Callable[..., ParamConstraint] = ParamConstraint
        parameter = constructor(
            name="allocation_method",
            dtype="str",
            allowed_values=source,
        )
        spec = replace(_make_v2_spec(), parameter_schema=(parameter,))
        original_hash = canonical_spec_hash(spec)

        source.append("risk_parity")

        assert parameter.allowed_values == ("equal_weight", "score_weight")
        assert canonical_spec_hash(spec) == original_hash

    def test_hash_is_full_lowercase_sha256(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_hash

        spec_hash = canonical_spec_hash(_make_v2_spec())

        assert re.fullmatch(r"[0-9a-f]{64}", spec_hash)

    def test_each_execution_field_change_changes_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_hash
        from ditto_strategy.alpha.specs import StrategyKind

        spec = _make_v2_spec()
        factor_node = next(
            node for node in spec.pipeline.nodes if node.node_id == "factors"
        )
        changed_node = replace(
            factor_node,
            config={"lookback": 120, "weights": {"momentum": 0.6, "value": 0.4}},
        )
        changed_pipeline = replace(
            spec.pipeline,
            nodes=tuple(
                changed_node if node.node_id == "factors" else node
                for node in spec.pipeline.nodes
            ),
        )
        variants = (
            replace(spec, strategy_family_id="other-family"),
            replace(spec, strategy_kind=StrategyKind.ETF_ROTATION),
            replace(spec, pipeline=changed_pipeline),
            replace(
                spec,
                parameter_schema=(replace(spec.parameter_schema[0], max_value=240),),
            ),
        )
        baseline_hash = canonical_spec_hash(spec)

        assert all(
            canonical_spec_hash(variant) != baseline_hash for variant in variants
        )

    @pytest.mark.parametrize(
        ("field_name", "legal_value"),
        [
            pytest.param("min_value", 10.0, id="minimum"),
            pytest.param("max_value", 240.0, id="maximum"),
            pytest.param("step", 10.0, id="step"),
        ],
    )
    def test_each_legal_parameter_identity_field_changes_hash(
        self,
        field_name: str,
        legal_value: float,
    ) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_hash

        spec = _make_v2_spec()
        changed_parameter = replace(
            spec.parameter_schema[0],
            **{field_name: legal_value},
        )

        assert canonical_spec_hash(
            replace(spec, parameter_schema=(changed_parameter,)),
        ) != canonical_spec_hash(spec)

    def test_codec_rejects_non_finite_parameter_even_if_domain_is_bypassed(
        self,
    ) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        object.__setattr__(spec.parameter_schema[0], "step", float("nan"))

        with pytest.raises(StrategySpecError, match="canonical"):
            canonical_spec_bytes(spec)

    @pytest.mark.parametrize(
        ("field_name", "invalid_value", "expected_reason"),
        [
            pytest.param("name", True, "invalid_parameter_name", id="bool-name"),
            pytest.param(
                "dtype",
                "decimal",
                "invalid_parameter_dtype",
                id="unsupported-dtype",
            ),
            pytest.param(
                "allowed_values",
                ("equal_weight", True),
                "invalid_parameter_allowed_values",
                id="bool-allowed-value",
            ),
            pytest.param(
                "min_value",
                True,
                "non_finite_parameter_identity",
                id="bool-minimum",
            ),
            pytest.param(
                "min_value",
                10**1000,
                "non_finite_parameter_identity",
                id="huge-integer-minimum",
            ),
        ],
    )
    def test_codec_revalidates_parameter_identity_after_domain_bypass(
        self,
        field_name: str,
        invalid_value: object,
        expected_reason: str,
    ) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        parameter = spec.parameter_schema[0]
        object.__setattr__(parameter, field_name, invalid_value)

        with pytest.raises(StrategySpecError) as exc_info:
            canonical_spec_bytes(spec)

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == expected_reason

    def test_codec_rejects_non_string_mapping_key_after_domain_bypass(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        factor_node = next(
            node for node in spec.pipeline.nodes if node.node_id == "factors"
        )
        object.__setattr__(factor_node, "config", {1: "not-canonical"})

        with pytest.raises(StrategySpecError, match=r"key|canonical"):
            canonical_spec_bytes(spec)

    def test_orjson_serialization_failure_is_wrapped_as_domain_error(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        factor_node = next(
            node for node in spec.pipeline.nodes if node.node_id == "factors"
        )
        object.__setattr__(factor_node, "config", {"too_large": 1 << 128})

        with pytest.raises(StrategySpecError, match="canonical"):
            canonical_spec_bytes(spec)

    def test_ui_metadata_name_and_tags_do_not_change_execution_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        renamed = replace(
            spec,
            name="重命名不应影响执行",
            metadata={"layout": {"x": 999}, "color": "blue"},
            tags=("published", "favorite"),
        )

        canonical = canonical_spec_bytes(spec)
        payload = orjson.loads(canonical)
        assert canonical_spec_bytes(renamed) == canonical
        assert "name" not in payload
        assert "metadata" not in payload
        assert "tags" not in payload

    def test_codec_requires_explicit_legacy_adapter(self) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        legacy_as_v2 = cast(StrategySpecV2, _make_legacy_spec())

        with pytest.raises(StrategySpecError, match="StrategySpecV2"):
            canonical_spec_bytes(legacy_as_v2)

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(float("nan"), id="non-finite-float"),
            pytest.param(object(), id="unsupported-object"),
        ],
    )
    def test_rejects_values_without_a_canonical_json_identity(
        self,
        invalid_value: object,
    ) -> None:
        from ditto_strategy.alpha.spec_codec import canonical_spec_bytes

        spec = _make_v2_spec()
        factor_node = next(
            node for node in spec.pipeline.nodes if node.node_id == "factors"
        )
        object.__setattr__(factor_node, "config", {"invalid": invalid_value})

        with pytest.raises(StrategySpecError, match="canonical"):
            canonical_spec_bytes(spec)


class TestLegacyStrategySpecAdapter:
    """Legacy seed 只能通过显式 adapter 获得完整 V2 执行身份。"""

    def test_adapter_maps_semantics_to_typed_nodes_not_an_opaque_blob(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory
        from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
        from ditto_strategy.alpha.specs import StrategyKind, StrategySpecV2

        adapted = adapt_legacy_strategy_spec(_make_legacy_spec())
        categories = tuple(
            node.category
            for node in sorted(
                adapted.pipeline.nodes,
                key=lambda node: adapted.pipeline.sequence.index(node.node_id),
            )
        )

        assert isinstance(adapted, StrategySpecV2)
        assert adapted.strategy_kind is StrategyKind.ETF_ROTATION
        assert categories == (
            NodeCategory.UNIVERSE,
            NodeCategory.FACTOR_SET,
            NodeCategory.SCORER,
            NodeCategory.SELECTOR,
            NodeCategory.ALLOCATOR,
            NodeCategory.EXECUTION_ASSUMPTION,
            NodeCategory.VALIDATION,
        )
        assert all(
            node.ref.node_type != "legacy.spec" for node in adapted.pipeline.nodes
        )

    def test_adapter_rejects_non_legacy_spec(self) -> None:
        from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec

        v2_as_legacy = cast(StrategySpec, _make_v2_spec())

        with pytest.raises(StrategySpecError, match="legacy"):
            adapt_legacy_strategy_spec(v2_as_legacy)

    def test_every_legacy_execution_field_participates_in_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
        )

        base = _make_legacy_spec()
        variants = (
            ("template", replace(base, template="etf_trend_swing")),
            ("universe", replace(base, universe="other_universe")),
            ("asset_class", replace(base, asset_class="stock")),
            ("scorer", replace(base, scorer=ScorerSpec(method="zscore"))),
            ("selector", replace(base, selector=SelectorSpec(params={"k": 5}))),
            (
                "execution",
                replace(
                    base,
                    execution=replace(
                        base.execution,
                        default_order_type=OrderType.LIMIT,
                    ),
                ),
            ),
            (
                "constraints",
                replace(
                    base,
                    constraints=(
                        replace(base.constraints[0], params={"max_weight": 0.2}),
                    ),
                ),
            ),
            ("benchmark", replace(base, benchmark="000905.SH")),
            ("params", replace(base, params={"lookback": 120, "cash_target": 0.05})),
            (
                "param_constraints",
                replace(
                    base,
                    param_constraints=(
                        replace(base.param_constraints[0], max_value=240),
                    ),
                ),
            ),
            (
                "signal_expressions",
                replace(
                    base,
                    signal_expressions=("momentum_3m", "volatility_factor"),
                ),
            ),
            ("signal_weights", replace(base, signal_weights=(0.6, 0.4))),
            (
                "required_datasets",
                replace(base, required_datasets=("etf_daily", "adj_factor")),
            ),
        )
        baseline_hash = canonical_spec_hash(adapt_legacy_strategy_spec(base))

        for field_name, variant in variants:
            assert (
                canonical_spec_hash(adapt_legacy_strategy_spec(variant))
                != baseline_hash
            ), field_name

    def test_legacy_name_and_tags_do_not_change_execution_hash(self) -> None:
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
        )

        base = _make_legacy_spec()
        renamed = replace(
            base,
            name="仅 UI 重命名",
            tags=("favorite", "published"),
        )

        assert canonical_spec_hash(
            adapt_legacy_strategy_spec(renamed),
        ) == canonical_spec_hash(adapt_legacy_strategy_spec(base))

    @pytest.mark.parametrize(
        "signal_expressions",
        [
            pytest.param(("momentum",), id="single-signal"),
            pytest.param(("momentum", "value"), id="multiple-signals"),
        ],
    )
    def test_empty_weights_hash_like_runtime_effective_unit_weights(
        self,
        signal_expressions: tuple[str, ...],
    ) -> None:
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
        )

        base = replace(
            _make_legacy_spec(),
            signal_expressions=signal_expressions,
            signal_weights=(),
        )
        explicit = replace(
            base,
            signal_weights=(1.0,) * len(signal_expressions),
        )

        assert canonical_spec_hash(
            adapt_legacy_strategy_spec(base),
        ) == canonical_spec_hash(adapt_legacy_strategy_spec(explicit))

    @pytest.mark.parametrize(
        ("signal_expressions", "different_weights"),
        [
            pytest.param(("momentum",), (0.5,), id="single-signal"),
            pytest.param(
                ("momentum", "value"),
                (1.0, 0.5),
                id="multiple-signals",
            ),
        ],
    )
    def test_different_effective_weights_have_different_hashes(
        self,
        signal_expressions: tuple[str, ...],
        different_weights: tuple[float, ...],
    ) -> None:
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
        )

        unit_weights = replace(
            _make_legacy_spec(),
            signal_expressions=signal_expressions,
            signal_weights=(1.0,) * len(signal_expressions),
        )
        changed = replace(unit_weights, signal_weights=different_weights)

        assert canonical_spec_hash(
            adapt_legacy_strategy_spec(unit_weights),
        ) != canonical_spec_hash(adapt_legacy_strategy_spec(changed))
