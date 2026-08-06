"""StrategySpec v2 节点值对象与基础受约束序列测试。"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError

import pytest
from ditto_strategy.errors import StrategySpecError


def _node(
    node_id: str,
    category: object,
    *,
    node_type: str | None = None,
) -> object:
    from ditto_strategy.alpha.nodes import NodeInstance, NodeRef

    resolved_type = node_type or node_id.replace("_", ".")
    return NodeInstance(
        node_id=node_id,
        ref=NodeRef(node_type=resolved_type, version="1"),
        category=category,
        config={},
    )


class TestNodeCategory:
    """节点类别是固定、可序列化的领域枚举。"""

    def test_has_only_the_constrained_pipeline_categories(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory

        assert tuple(category.value for category in NodeCategory) == (
            "universe",
            "factor_set",
            "filter",
            "scorer",
            "selector",
            "allocator",
            "execution_assumption",
            "validation",
        )


class TestNodeRef:
    """节点实现身份由稳定的 ``node_type@version`` 唯一表达。"""

    def test_exposes_stable_identity(self) -> None:
        from ditto_strategy.alpha.nodes import NodeRef

        ref = NodeRef(node_type="builtin.factor_set", version="2")

        assert ref.identity == "builtin.factor_set@2"

    @pytest.mark.parametrize(
        ("node_type", "version"),
        [
            pytest.param("", "1", id="empty-node-type"),
            pytest.param("builtin.factor", "", id="empty-version"),
            pytest.param("builtin@factor", "1", id="ambiguous-node-type"),
            pytest.param("builtin.factor", "1@draft", id="ambiguous-version"),
        ],
    )
    def test_rejects_invalid_identity_parts(
        self,
        node_type: str,
        version: str,
    ) -> None:
        from ditto_strategy.alpha.nodes import NodeRef

        with pytest.raises(StrategySpecError, match=r"node_type|version"):
            NodeRef(node_type=node_type, version=version)

    def test_is_frozen(self) -> None:
        from ditto_strategy.alpha.nodes import NodeRef

        ref = NodeRef(node_type="builtin.factor_set", version="1")

        with pytest.raises(FrozenInstanceError):
            ref.version = "2"  # type: ignore[misc]


class TestPipelineSpec:
    """PipelineSpec 只冻结基础 sequence，不抢做 registry/cardinality。"""

    def test_accepts_legal_sequence_with_repeated_filters(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, PipelineSpec

        nodes = (
            _node("universe", NodeCategory.UNIVERSE),
            _node("factors", NodeCategory.FACTOR_SET),
            _node("liquidity_filter", NodeCategory.FILTER),
            _node("status_filter", NodeCategory.FILTER),
            _node("scorer", NodeCategory.SCORER),
            _node("selector", NodeCategory.SELECTOR),
            _node("allocator", NodeCategory.ALLOCATOR),
            _node("execution", NodeCategory.EXECUTION_ASSUMPTION),
            _node("validation", NodeCategory.VALIDATION),
        )

        pipeline = PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        )

        assert pipeline.sequence[2:4] == ("liquidity_filter", "status_filter")

    def test_rejects_duplicate_node_ids(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, PipelineSpec

        with pytest.raises(StrategySpecError, match="node_id"):
            PipelineSpec(
                nodes=(
                    _node("duplicate", NodeCategory.UNIVERSE),
                    _node("duplicate", NodeCategory.FACTOR_SET),
                ),
                sequence=("duplicate",),
            )

    @pytest.mark.parametrize(
        "sequence",
        [
            pytest.param(("universe",), id="missing-node"),
            pytest.param(("universe", "missing"), id="unknown-node"),
            pytest.param(("universe", "universe", "factors"), id="duplicate-ref"),
        ],
    )
    def test_sequence_must_reference_every_node_exactly_once(
        self,
        sequence: tuple[str, ...],
    ) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, PipelineSpec

        with pytest.raises(StrategySpecError, match="sequence"):
            PipelineSpec(
                nodes=(
                    _node("universe", NodeCategory.UNIVERSE),
                    _node("factors", NodeCategory.FACTOR_SET),
                ),
                sequence=sequence,
            )

    def test_rejects_category_order_reversal(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, PipelineSpec

        with pytest.raises(StrategySpecError, match=r"category|sequence"):
            PipelineSpec(
                nodes=(
                    _node("scorer", NodeCategory.SCORER),
                    _node("late_filter", NodeCategory.FILTER),
                ),
                sequence=("scorer", "late_filter"),
            )

    @pytest.mark.parametrize(
        ("field_name", "invalid_value"),
        [
            pytest.param("nodes", [], id="nodes-list"),
            pytest.param("nodes", None, id="nodes-none"),
            pytest.param("nodes", (object(),), id="nodes-invalid-element"),
            pytest.param("sequence", [], id="sequence-list"),
            pytest.param("sequence", None, id="sequence-none"),
            pytest.param("sequence", (object(),), id="sequence-invalid-element"),
        ],
    )
    def test_programmatic_boundaries_require_typed_tuples(
        self,
        field_name: str,
        invalid_value: object,
    ) -> None:
        from ditto_strategy.alpha.nodes import (
            NodeCategory,
            NodeInstance,
            NodeRef,
            PipelineSpec,
        )

        node = NodeInstance(
            node_id="universe",
            ref=NodeRef("builtin.universe", "1"),
            category=NodeCategory.UNIVERSE,
        )
        values: dict[str, object] = {
            "nodes": (node,),
            "sequence": ("universe",),
        }
        values[field_name] = invalid_value
        constructor: Callable[..., PipelineSpec] = PipelineSpec

        with pytest.raises(StrategySpecError, match=field_name):
            constructor(**values)


class TestNodeInstanceCanonicalConfig:
    def test_rejects_self_referential_config_with_typed_field_path(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, NodeInstance, NodeRef

        source: dict[str, object] = {}
        source["self"] = source

        with pytest.raises(StrategySpecError) as exc_info:
            NodeInstance(
                node_id="factors",
                ref=NodeRef("builtin.factor_set", "1"),
                category=NodeCategory.FACTOR_SET,
                config=source,
            )

        assert exc_info.value.details["reason"] == "cyclic_canonical_json_value"
        assert exc_info.value.details["field_name"] == "config.self"

    def test_config_is_a_recursive_immutable_snapshot(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, NodeInstance, NodeRef

        source: dict[str, object] = {
            "nested": {"weights": [0.4, 0.6]},
        }
        node = NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
            config=source,
        )
        nested = node.config["nested"]
        assert isinstance(nested, Mapping)
        weights = nested["weights"]
        assert isinstance(weights, tuple)

        with pytest.raises(TypeError):
            operator.setitem(node.config, "added", True)
        with pytest.raises(TypeError):
            operator.setitem(nested, "added", True)
        with pytest.raises(TypeError):
            operator.setitem(weights, 0, 1.0)

        source_nested = source["nested"]
        assert isinstance(source_nested, dict)
        source_nested["weights"] = [1.0]
        assert nested["weights"] == (0.4, 0.6)

    def test_legal_mapping_and_json_sequence_values_are_preserved(self) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, NodeInstance, NodeRef

        node = NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
            config={"factor_ids": ["momentum", "value"]},
        )

        assert node.config["factor_ids"] == ("momentum", "value")

    def test_nested_config_normalizes_signed_zero_at_every_sequence_depth(
        self,
    ) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, NodeInstance, NodeRef

        source: dict[str, object] = {
            "outer": [
                {
                    "inner": (
                        -0.0,
                        {"deeper": [-0.0, -5.0]},
                    ),
                },
            ],
        }
        node = NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
            config=source,
        )
        outer = node.config["outer"]
        assert isinstance(outer, tuple)
        nested = outer[0]
        assert isinstance(nested, Mapping)
        inner = nested["inner"]
        assert isinstance(inner, tuple)
        deeper = inner[1]
        assert isinstance(deeper, Mapping)
        values = deeper["deeper"]
        assert isinstance(values, tuple)

        assert math.copysign(1.0, inner[0]) == 1.0
        assert math.copysign(1.0, values[0]) == 1.0
        assert math.copysign(1.0, values[1]) == -1.0

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(float("nan"), id="nan"),
            pytest.param(float("inf"), id="positive-infinity"),
            pytest.param(float("-inf"), id="negative-infinity"),
        ],
    )
    def test_nested_config_rejects_non_finite_float_with_typed_error(
        self,
        invalid_value: float,
    ) -> None:
        from ditto_strategy.alpha.nodes import NodeCategory, NodeInstance, NodeRef

        with pytest.raises(StrategySpecError) as exc_info:
            NodeInstance(
                node_id="factors",
                ref=NodeRef("builtin.factor_set", "1"),
                category=NodeCategory.FACTOR_SET,
                config={"outer": [{"threshold": invalid_value}]},
            )

        assert exc_info.value.details["field_name"] == "config.outer[0].threshold"
        assert exc_info.value.details["reason"] == "invalid_canonical_json_value"
