"""NodeDescriptor registry 与受约束流水线编译器单元测试。"""

from __future__ import annotations

import operator
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace

import pytest
from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.specs import StrategyKind
from ditto_strategy.errors import StrategySpecError


def _descriptor(
    *,
    node_type: str,
    category: NodeCategory,
    input_contract: str,
    output_contract: str,
    display_name: str | None = None,
    implementation_key: str | None = None,
    origin: str = "builtin",
) -> object:
    from ditto_strategy.alpha.node_registry import (
        NodeConfigType,
        NodeDescriptor,
    )

    return NodeDescriptor(
        node_type=node_type,
        version="1",
        category=category,
        display_name=display_name or node_type,
        input_contract=input_contract,
        output_contract=output_contract,
        config_schema={"label": NodeConfigType.STRING},
        default_config={"label": "default"},
        required_datasets=("etf_daily",),
        capability_tags=("deterministic",),
        supported_strategy_kinds=(StrategyKind.ETF_ROTATION,),
        deterministic=True,
        implementation_key=implementation_key or f"{node_type}.v1",
        executor_contract_version="1",
        origin=origin,
    )


def _golden_descriptors(
    *,
    scorer_input: str = "factor_frame.v1",
) -> tuple[object, ...]:
    categories = (
        (
            "test.universe",
            NodeCategory.UNIVERSE,
            "decision_frame.v1",
            "universe_frame.v1",
        ),
        (
            "test.factor_set",
            NodeCategory.FACTOR_SET,
            "universe_frame.v1",
            "factor_frame.v1",
        ),
        (
            "test.filter",
            NodeCategory.FILTER,
            "factor_frame.v1",
            "factor_frame.v1",
        ),
        (
            "test.scorer",
            NodeCategory.SCORER,
            scorer_input,
            "scored_frame.v1",
        ),
        (
            "test.selector",
            NodeCategory.SELECTOR,
            "scored_frame.v1",
            "selected_frame.v1",
        ),
        (
            "test.allocator",
            NodeCategory.ALLOCATOR,
            "selected_frame.v1",
            "allocated_frame.v1",
        ),
        (
            "test.execution",
            NodeCategory.EXECUTION_ASSUMPTION,
            "allocated_frame.v1",
            "execution_frame.v1",
        ),
        (
            "test.validation",
            NodeCategory.VALIDATION,
            "execution_frame.v1",
            "validated_frame.v1",
        ),
    )
    return tuple(
        _descriptor(
            node_type=node_type,
            category=category,
            input_contract=input_contract,
            output_contract=output_contract,
        )
        for node_type, category, input_contract, output_contract in categories
    )


def _golden_pipeline(*, filter_count: int = 0) -> PipelineSpec:
    nodes = [
        NodeInstance(
            node_id="universe",
            ref=NodeRef("test.universe", "1"),
            category=NodeCategory.UNIVERSE,
        ),
        NodeInstance(
            node_id="factors",
            ref=NodeRef("test.factor_set", "1"),
            category=NodeCategory.FACTOR_SET,
        ),
    ]
    nodes.extend(
        NodeInstance(
            node_id=f"filter_{index}",
            ref=NodeRef("test.filter", "1"),
            category=NodeCategory.FILTER,
        )
        for index in range(filter_count)
    )
    nodes.extend(
        (
            NodeInstance(
                node_id="scorer",
                ref=NodeRef("test.scorer", "1"),
                category=NodeCategory.SCORER,
            ),
            NodeInstance(
                node_id="selector",
                ref=NodeRef("test.selector", "1"),
                category=NodeCategory.SELECTOR,
            ),
            NodeInstance(
                node_id="allocator",
                ref=NodeRef("test.allocator", "1"),
                category=NodeCategory.ALLOCATOR,
            ),
            NodeInstance(
                node_id="execution",
                ref=NodeRef("test.execution", "1"),
                category=NodeCategory.EXECUTION_ASSUMPTION,
            ),
            NodeInstance(
                node_id="validation",
                ref=NodeRef("test.validation", "1"),
                category=NodeCategory.VALIDATION,
            ),
        ),
    )
    return PipelineSpec(
        nodes=tuple(nodes),
        sequence=tuple(node.node_id for node in nodes),
    )


class TestNodeDescriptor:
    def test_is_frozen_and_owns_typed_immutable_schemas(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeConfigType, NodeDescriptor

        descriptor = _descriptor(
            node_type="builtin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
        )

        assert isinstance(descriptor, NodeDescriptor)
        assert descriptor.config_schema["label"] is NodeConfigType.STRING
        assert descriptor.default_config["label"] == "default"
        with pytest.raises(FrozenInstanceError):
            descriptor.display_name = "changed"  # type: ignore[misc]
        with pytest.raises(TypeError):
            operator.setitem(descriptor.config_schema, "added", NodeConfigType.JSON)
        with pytest.raises(TypeError):
            operator.setitem(descriptor.default_config, "label", "changed")

    def test_schema_may_require_config_without_defining_a_default(self) -> None:
        from ditto_strategy.alpha.node_registry import (
            NodeConfigType,
            NodeDescriptor,
        )

        descriptor = NodeDescriptor(
            node_type="builtin.required_filter",
            version="1",
            category=NodeCategory.FILTER,
            display_name="Required filter",
            input_contract="signal_frame.v1",
            output_contract="signal_frame.v1",
            config_schema={"threshold": NodeConfigType.NUMBER},
            default_config={},
            supported_strategy_kinds=(StrategyKind.ETF_ROTATION,),
            implementation_key="builtin.required_filter.v1",
        )

        assert descriptor.resolve_config({"threshold": 0.25})["threshold"] == 0.25
        with pytest.raises(StrategySpecError, match="missing"):
            descriptor.resolve_config({})


class TestNodeRegistry:
    def test_manifest_hash_is_stable_and_excludes_display_text(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry

        first = _descriptor(
            node_type="builtin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
            display_name="Factor Set",
        )
        second = replace(first, display_name="因子集合")

        assert (
            NodeRegistry((first,)).manifest_hash
            == NodeRegistry(
                (second,),
            ).manifest_hash
        )
        assert len(NodeRegistry((first,)).manifest_hash) == 64

    def test_manifest_hash_canonicalizes_set_like_descriptor_fields(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry

        descriptor = _descriptor(
            node_type="builtin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
        )
        descriptor = replace(
            descriptor,
            required_datasets=("etf_daily", "trading_calendar"),
            capability_tags=("deterministic", "daily"),
            supported_strategy_kinds=(
                StrategyKind.ETF_ROTATION,
                StrategyKind.STOCK_SELECTION,
            ),
        )
        reordered = replace(
            descriptor,
            required_datasets=tuple(reversed(descriptor.required_datasets)),
            capability_tags=tuple(reversed(descriptor.capability_tags)),
            supported_strategy_kinds=tuple(
                reversed(descriptor.supported_strategy_kinds)
            ),
        )

        assert (
            NodeRegistry((descriptor,)).manifest_hash
            == NodeRegistry(
                (reordered,),
            ).manifest_hash
        )

    def test_manifest_hash_changes_with_execution_identity(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry

        descriptor = _descriptor(
            node_type="builtin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
        )

        changed = replace(descriptor, implementation_key="builtin.factor_set.v2")

        assert (
            NodeRegistry((descriptor,)).manifest_hash
            != NodeRegistry(
                (changed,),
            ).manifest_hash
        )

    def test_manifest_rejects_out_of_range_integer_with_typed_field_path(
        self,
    ) -> None:
        from ditto_strategy.alpha.node_registry import (
            NodeConfigType,
            NodeRegistry,
        )

        descriptor = _descriptor(
            node_type="builtin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
        )
        descriptor = replace(
            descriptor,
            config_schema={"lookback": NodeConfigType.INTEGER},
            default_config={"lookback": 2**100},
        )

        with pytest.raises(StrategySpecError) as exc_info:
            NodeRegistry((descriptor,))

        assert exc_info.value.details["reason"] == "invalid_descriptor_manifest_value"
        assert exc_info.value.details["field_name"] == (
            "descriptors.builtin.factor_set@1.default_config.lookback"
        )

    def test_lookup_is_exact_and_unknown_node_or_version_fails_closed(self) -> None:
        from ditto_strategy.alpha.node_registry import default_node_registry

        registry = default_node_registry()

        assert registry.lookup(NodeRef("legacy.universe", "1")).identity == (
            "legacy.universe@1"
        )
        with pytest.raises(StrategySpecError, match="unknown"):
            registry.lookup(NodeRef("legacy.unknown", "1"))
        with pytest.raises(StrategySpecError, match="unknown"):
            registry.lookup(NodeRef("legacy.universe", "999"))

    def test_rejects_non_builtin_origin_before_lookup(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry

        descriptor = _descriptor(
            node_type="plugin.factor_set",
            category=NodeCategory.FACTOR_SET,
            input_contract="universe_frame.v1",
            output_contract="factor_frame.v1",
            origin="plugin",
        )

        with pytest.raises(StrategySpecError, match="builtin"):
            NodeRegistry((descriptor,))


class TestConstrainedPipelineCompiler:
    def test_compiles_fixed_grammar_and_allows_repeated_filters(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        registry = NodeRegistry(_golden_descriptors())
        pipeline = _golden_pipeline(filter_count=2)

        compiled = compile_node_pipeline(
            pipeline,
            registry=registry,
            strategy_kind=StrategyKind.ETF_ROTATION,
        )

        assert tuple(node.node_id for node in compiled.nodes) == pipeline.sequence
        assert (
            tuple(node.category for node in compiled.nodes).count(
                NodeCategory.FILTER,
            )
            == 2
        )
        assert compiled.registry_manifest_hash == registry.manifest_hash

    @pytest.mark.parametrize(
        "category",
        tuple(NodeCategory)[:2] + tuple(NodeCategory)[3:],
    )
    def test_requires_exactly_one_non_filter_golden_node(
        self,
        category: NodeCategory,
    ) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        pipeline = _golden_pipeline()
        nodes = tuple(node for node in pipeline.nodes if node.category is not category)
        incomplete = PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        )

        with pytest.raises(StrategySpecError, match="cardinality"):
            compile_node_pipeline(
                incomplete,
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )

    def test_rejects_duplicate_non_filter_golden_node(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        pipeline = _golden_pipeline()
        nodes = list(pipeline.nodes)
        scorer_index = next(
            index
            for index, node in enumerate(nodes)
            if node.category is NodeCategory.SCORER
        )
        nodes.insert(
            scorer_index + 1,
            NodeInstance(
                node_id="scorer_copy",
                ref=NodeRef("test.scorer", "1"),
                category=NodeCategory.SCORER,
            ),
        )
        duplicate = PipelineSpec(
            nodes=tuple(nodes),
            sequence=tuple(node.node_id for node in nodes),
        )

        with pytest.raises(StrategySpecError, match="cardinality"):
            compile_node_pipeline(
                duplicate,
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )

    def test_rejects_descriptor_category_mismatch(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        pipeline = _golden_pipeline()
        nodes = tuple(
            replace(node, category=NodeCategory.FILTER)
            if node.node_id == "factors"
            else node
            for node in pipeline.nodes
        )
        mismatched = PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        )

        with pytest.raises(StrategySpecError, match="category"):
            compile_node_pipeline(
                mismatched,
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )

    def test_rejects_adjacent_port_contract_mismatch(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        with pytest.raises(StrategySpecError, match="port"):
            compile_node_pipeline(
                _golden_pipeline(),
                registry=NodeRegistry(
                    _golden_descriptors(scorer_input="other_frame.v1"),
                ),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )

    def test_rejects_unsupported_strategy_kind(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        with pytest.raises(StrategySpecError, match="strategy kind"):
            compile_node_pipeline(
                _golden_pipeline(),
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.STOCK_SELECTION,
            )

    def test_validates_config_schema_and_applies_defaults(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        pipeline = _golden_pipeline()
        compiled = compile_node_pipeline(
            pipeline,
            registry=NodeRegistry(_golden_descriptors()),
            strategy_kind=StrategyKind.ETF_ROTATION,
        )

        assert all(node.config["label"] == "default" for node in compiled.nodes)
        assert all(isinstance(node.config, Mapping) for node in compiled.nodes)

        nodes = tuple(
            replace(node, config={"label": 42}) if node.node_id == "scorer" else node
            for node in pipeline.nodes
        )
        invalid = PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        )
        with pytest.raises(StrategySpecError, match="config"):
            compile_node_pipeline(
                invalid,
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )

    def test_disabled_required_node_is_missing_not_silently_executed(self) -> None:
        from ditto_strategy.alpha.node_registry import NodeRegistry
        from ditto_strategy.alpha.pipeline import compile_node_pipeline

        pipeline = _golden_pipeline()
        nodes = tuple(
            replace(node, enabled=False) if node.node_id == "scorer" else node
            for node in pipeline.nodes
        )
        disabled = PipelineSpec(
            nodes=nodes,
            sequence=tuple(node.node_id for node in nodes),
        )

        with pytest.raises(StrategySpecError, match="cardinality"):
            compile_node_pipeline(
                disabled,
                registry=NodeRegistry(_golden_descriptors()),
                strategy_kind=StrategyKind.ETF_ROTATION,
            )
