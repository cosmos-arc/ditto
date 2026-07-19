"""Single typed legacy-to-v2 runtime compilation seam."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    ParameterBinder,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import StrategySpec, StrategySpecV2
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
)
from ditto_application.strategy_spec_deserialization import deserialize_strategy_spec


@dataclass(frozen=True)
class TypedLegacyRuntime:
    """Version-policy-neutral result of binding and compiling one exact record."""

    legacy_spec: StrategySpec
    base_spec: StrategySpecV2
    resolved_spec: StrategySpecV2
    pipeline: StrategyPipeline
    base_spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]
    node_registry_manifest_hash: str
    compiled_expressions: CompiledExpressions | None


def build_typed_legacy_runtime(
    *,
    record: StrategySpecRecord,
    candidate_parameters: tuple[CandidateParameter, ...],
    registry: NodeRegistry,
    node_pipeline_builder: NodePipelineBuilder,
) -> TypedLegacyRuntime:
    """Bind one exact legacy record and compile the existing runner once."""
    legacy_spec = deserialize_strategy_spec(record)
    base_spec = adapt_legacy_strategy_spec(legacy_spec)
    try:
        binding = ParameterBinder(registry=registry).bind(
            base_spec,
            candidate_parameters=candidate_parameters,
        )
    except StrategySpecError as exc:
        raise AppBuilderError(str(exc), details=exc.details) from exc
    pipeline = node_pipeline_builder.build(
        legacy_spec=legacy_spec,
        pipeline=binding.resolved_spec.pipeline,
        strategy_kind=binding.resolved_spec.strategy_kind,
    )
    return TypedLegacyRuntime(
        legacy_spec=legacy_spec,
        base_spec=binding.base_spec,
        resolved_spec=binding.resolved_spec,
        pipeline=pipeline,
        base_spec_hash=binding.base_spec_hash,
        resolved_spec_hash=binding.resolved_spec_hash,
        parameter_hash=binding.parameter_hash,
        effective_parameters=binding.effective_parameters,
        node_registry_manifest_hash=registry.manifest_hash,
        compiled_expressions=_compile_signal_expressions(legacy_spec),
    )


def _compile_signal_expressions(
    spec: StrategySpec,
) -> CompiledExpressions | None:
    if not spec.signal_expressions:
        return None
    return FactorBridge().compile_and_validate(
        expressions=spec.signal_expressions,
        weights=spec.signal_weights or (1.0,) * len(spec.signal_expressions),
    )
