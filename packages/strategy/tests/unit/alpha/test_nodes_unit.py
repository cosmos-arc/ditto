"""StrategySpec v2 节点值对象与基础受约束序列测试。"""

from __future__ import annotations

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
