"""受约束节点编译结果到现有 ``StrategyPipeline`` 的 builtin 装配。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ditto_strategy.alpha.builtins.filtering import TrendFilterStage
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.nodes import PipelineSpec
from ditto_strategy.alpha.pipeline import (
    CompiledNode,
    StrategyPipeline,
    compile_node_pipeline,
)
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import StrategyKind, StrategySpec

from ditto_application.builders._spec_deserializer import (
    read_float,
    read_str_value,
)
from ditto_application.builders.template_builders import (
    build_legacy_node_stage_groups,
)
from ditto_application.exceptions import AppBuilderError

__all__ = ["NodePipelineBuilder"]


def _build_trend_filter(
    config: Mapping[str, object],
) -> tuple[DecisionStage, ...]:
    return (
        TrendFilterStage(
            threshold=read_float(
                config["threshold"],
                field_name="node.config.threshold",
            ),
            direction=read_str_value(
                config["direction"],
                field_name="node.config.direction",
            ),
            signal_column=read_str_value(
                config["signal_column"],
                field_name="node.config.signal_column",
            ),
        ),
    )


class NodePipelineBuilder:
    """只解析显式 builtin implementation key，不做 import/discovery。"""

    def __init__(self, *, registry: NodeRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> NodeRegistry:
        """暴露只读 registry，供 composition/evidence 检查 manifest。"""
        return self._registry

    def build(
        self,
        *,
        legacy_spec: StrategySpec,
        pipeline: PipelineSpec,
        strategy_kind: StrategyKind,
    ) -> StrategyPipeline:
        """经 compiler 和 versioned legacy adapter 构造唯一现有 runner。"""
        compiled = compile_node_pipeline(
            pipeline,
            registry=self._registry,
            strategy_kind=strategy_kind,
        )
        legacy_groups = build_legacy_node_stage_groups(legacy_spec)
        stages: list[DecisionStage] = []
        for node in compiled.nodes:
            stages.extend(
                self._resolve_builtin_stages(
                    node,
                    legacy_groups=legacy_groups,
                ),
            )
        return StrategyPipeline(stages)

    @staticmethod
    def _resolve_builtin_stages(
        node: CompiledNode,
        *,
        legacy_groups: Mapping[str, Sequence[DecisionStage]],
    ) -> Sequence[DecisionStage]:
        implementation_key = node.implementation_key
        legacy_stages = legacy_groups.get(implementation_key)
        if legacy_stages is not None:
            return legacy_stages
        if implementation_key == "builtin.trend_filter.v1":
            return _build_trend_filter(node.config)
        msg = (
            "unknown builtin implementation_key: "
            f"{implementation_key} (node_id={node.node_id})"
        )
        raise AppBuilderError(
            msg,
            details={
                "reason": "unknown_implementation_key",
                "implementation_key": implementation_key,
                "node_id": node.node_id,
            },
        )
