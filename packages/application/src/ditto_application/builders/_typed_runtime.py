"""Single typed legacy-to-v2 runtime compilation seam."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.builtins.scoring import FactorScoreColumnBinding
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    ParameterBinder,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import StrategySpec, StrategySpecV2
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.node_pipeline_builder import (
    AttestedNodePipeline,
    NodePipelineBuilder,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
    factor_normalized_column,
    factor_value_column,
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
    pipeline_execution_hash: str | None
    attested_pipeline: AttestedNodePipeline | None
    compiled_expressions: CompiledExpressions | None


def build_typed_legacy_runtime(
    *,
    record: StrategySpecRecord,
    candidate_parameters: tuple[CandidateParameter, ...],
    registry: NodeRegistry,
    node_pipeline_builder: NodePipelineBuilder,
    evidence_sink: SelectionEvidenceSink | None = None,
    factor_bridge: FactorBridge | None = None,
    require_pipeline_attestation: bool = False,
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
    compiled_expressions = _compile_signal_expressions(
        legacy_spec,
        factor_bridge=factor_bridge,
    )
    factor_bindings = (
        _compiled_factor_bindings(legacy_spec, compiled_expressions)
        if evidence_sink is not None
        else ()
    )
    pipeline_execution_hash: str | None = None
    attested_pipeline: AttestedNodePipeline | None = None
    if require_pipeline_attestation:
        attested = NodePipelineBuilder.build_attested(
            node_pipeline_builder,
            legacy_spec=legacy_spec,
            pipeline=binding.resolved_spec.pipeline,
            strategy_kind=binding.resolved_spec.strategy_kind,
            factor_bindings=factor_bindings,
            evidence_sink=evidence_sink,
        )
        pipeline = attested.pipeline
        pipeline_execution_hash = attested.execution_hash
        attested_pipeline = attested
    else:
        pipeline = node_pipeline_builder.build(
            legacy_spec=legacy_spec,
            pipeline=binding.resolved_spec.pipeline,
            strategy_kind=binding.resolved_spec.strategy_kind,
            factor_bindings=factor_bindings,
            evidence_sink=evidence_sink,
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
        pipeline_execution_hash=pipeline_execution_hash,
        attested_pipeline=attested_pipeline,
        compiled_expressions=compiled_expressions,
    )


def _compiled_factor_bindings(
    spec: StrategySpec,
    compiled: CompiledExpressions | None,
) -> tuple[FactorScoreColumnBinding, ...]:
    """Bind only compiler-proven factor identities to materialized score columns."""
    if compiled is None:
        return ()
    aggregated: dict[str, FactorScoreColumnBinding] = {}
    for index, factor_id in enumerate(spec.signal_expressions):
        existing = aggregated.get(factor_id)
        if existing is None:
            aggregated[factor_id] = FactorScoreColumnBinding(
                factor_id=factor_id,
                raw_column=factor_value_column(index),
                processed_column=factor_value_column(index),
                normalized_column=factor_normalized_column(index),
                weight=compiled.weights[index],
            )
        else:
            aggregated[factor_id] = FactorScoreColumnBinding(
                factor_id=existing.factor_id,
                raw_column=existing.raw_column,
                processed_column=existing.processed_column,
                normalized_column=existing.normalized_column,
                weight=existing.weight + compiled.weights[index],
            )
    return tuple(aggregated.values())


def _compile_signal_expressions(
    spec: StrategySpec,
    *,
    factor_bridge: FactorBridge | None,
) -> CompiledExpressions | None:
    if not spec.signal_expressions:
        return None
    bridge = factor_bridge if factor_bridge is not None else FactorBridge()
    return bridge.compile_and_validate(
        expressions=spec.signal_expressions,
        weights=spec.signal_weights or (1.0,) * len(spec.signal_expressions),
    )
