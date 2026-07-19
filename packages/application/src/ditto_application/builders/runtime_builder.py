"""
已发布策略 Spec 的运行时装配器.

Facade 委托到 deserialization + template_builders 子模块.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.node_registry import NodeRegistry, default_node_registry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.specs import StrategySpec, StrategySpecV2
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders._typed_runtime import (
    build_typed_legacy_runtime,
)
from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
)

__all__ = [
    "PublishedStrategyRuntime",
    "StrategyRuntimeBuilder",
]


# ===========================================================================
# PublishedStrategyRuntime
# ===========================================================================


@dataclass(frozen=True)
class PublishedStrategyRuntime:
    """已发布策略的运行时定义。"""

    record: StrategySpecRecord
    spec: StrategySpec
    base_spec: StrategySpecV2
    resolved_spec: StrategySpecV2
    pipeline: StrategyPipeline
    base_spec_hash: str
    spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]
    compiled_expressions: CompiledExpressions | None = None


# ===========================================================================
# StrategyRuntimeBuilder
# ===========================================================================


class StrategyRuntimeBuilder:
    """从 published StrategySpecRecord 组装 Core runtime 对象。"""

    def __init__(
        self,
        *,
        catalog_service: StrategyCatalogReader,
        node_registry: NodeRegistry | None = None,
        node_pipeline_builder: NodePipelineBuilder | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        registry = node_registry or default_node_registry()
        self._node_registry = registry
        self._node_pipeline_builder = node_pipeline_builder or NodePipelineBuilder(
            registry=registry,
        )

    def build_published_runtime(
        self,
        strategy_id: str,
        version: int | None = None,
        *,
        candidate_parameters: tuple[CandidateParameter, ...] = (),
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> PublishedStrategyRuntime:
        """读取 published spec 并构造 ``StrategySpec + StrategyPipeline``。"""
        record = (
            self._catalog_service.get_latest_published(strategy_id)
            if version is None
            else self._catalog_service.get_spec(strategy_id, version)
        )
        if record is None:
            msg = (
                f"未找到策略定义: strategy_id={strategy_id}, "
                f"version={version if version is not None else 'latest'}"
            )
            raise AppBuilderError(msg)
        if record.status != "published":
            msg = (
                f"策略定义尚未发布为 published: strategy_id={strategy_id}, "
                f"version={record.version}, status={record.status}"
            )
            raise AppBuilderError(msg)

        resolved = build_typed_legacy_runtime(
            record=record,
            candidate_parameters=candidate_parameters,
            registry=self._node_registry,
            node_pipeline_builder=self._node_pipeline_builder,
            evidence_sink=evidence_sink,
        )
        return PublishedStrategyRuntime(
            record=record,
            spec=resolved.legacy_spec,
            base_spec=resolved.base_spec,
            resolved_spec=resolved.resolved_spec,
            pipeline=resolved.pipeline,
            compiled_expressions=resolved.compiled_expressions,
            base_spec_hash=resolved.base_spec_hash,
            spec_hash=resolved.resolved_spec_hash,
            parameter_hash=resolved.parameter_hash,
            effective_parameters=resolved.effective_parameters,
        )
