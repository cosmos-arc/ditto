"""受约束节点编译结果到现有 ``StrategyPipeline`` 的 builtin 装配。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import NoReturn, cast

import orjson
from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha._canonical_values import canonical_json_value
from ditto_strategy.alpha.builtins.filtering import TrendFilterStage
from ditto_strategy.alpha.builtins.scoring import FactorScoreColumnBinding
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.nodes import PipelineSpec
from ditto_strategy.alpha.pipeline import (
    CompiledNode,
    CompiledNodePipeline,
    StrategyPipeline,
    compile_node_pipeline,
)
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategyKind,
    StrategySpec,
)

from ditto_application.builders._spec_deserializer import (
    as_float_tuple,
    as_sequence,
    as_str_tuple,
    read_float,
    read_int,
    read_optional_str,
    read_str_value,
)
from ditto_application.builders.template_builders import (
    build_legacy_node_stage_groups,
)
from ditto_application.exceptions import AppBuilderError

__all__ = ["AttestedNodePipeline", "NodePipelineBuilder"]

_PIPELINE_EXECUTION_SCHEMA_VERSION = 1
_PIPELINE_EXECUTOR_CONTRACT = "ditto_application.node_pipeline_builder.v1"
_UNRESOLVED_EXECUTION_STATE = object()

_LEGACY_EXECUTING_IMPLEMENTATION_KEYS = frozenset(
    {
        "legacy.factor_set.v1",
        "legacy.scorer.v1",
        "legacy.selector.v1",
        "legacy.allocator.v1",
    },
)
_LEGACY_METADATA_IMPLEMENTATION_KEYS = frozenset(
    {
        "legacy.universe.v1",
        "legacy.execution_assumption.v1",
        "legacy.validation.v1",
    },
)
_LEGACY_IMPLEMENTATION_KEYS = (
    _LEGACY_EXECUTING_IMPLEMENTATION_KEYS | _LEGACY_METADATA_IMPLEMENTATION_KEYS
)
_SUPPORTED_IMPLEMENTATION_KEYS = _LEGACY_IMPLEMENTATION_KEYS | {
    "builtin.trend_filter.v1",
}


@dataclass(frozen=True)
class _LegacyRuntimeView:
    """由 compiled configs 重建的不可变 legacy factory 输入。"""

    spec: StrategySpec
    metadata_configs: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True, slots=True, init=False)
class AttestedNodePipeline:
    """Sealed concrete runner plus its independently verifiable execution proof."""

    _pipeline: StrategyPipeline
    _compiled: CompiledNodePipeline
    _execution_hash: str
    _evidence_sink: SelectionEvidenceSink | None
    _evidence_stage_indexes: tuple[int, ...]

    @property
    def pipeline(self) -> StrategyPipeline:
        """Return the concrete runner covered by this attestation."""
        return self._pipeline

    @property
    def execution_hash(self) -> str:
        """Return the digest of the compiled plan and actual stage state."""
        return self._execution_hash

    @property
    def evidence_sink(self) -> SelectionEvidenceSink | None:
        """Return the exact sink sealed with the concrete runner."""
        return self._evidence_sink

    def require_verified_pipeline(
        self, *, expected_execution_hash: str
    ) -> StrategyPipeline:
        """Recompute evidence from the runner that will actually be executed."""
        if type(self._pipeline) is not StrategyPipeline:
            _raise_adapter_error(
                "Attested research pipeline has an invalid runner",
                reason="invalid_attested_pipeline_runner",
            )
        stages = self._pipeline.stages
        if type(stages) is not tuple:
            _raise_adapter_error(
                "Attested research pipeline has invalid stages",
                reason="invalid_attested_pipeline_stages",
            )
        actual_hash = _pipeline_execution_hash(self._compiled, stages)
        if (
            actual_hash != self._execution_hash
            or actual_hash != expected_execution_hash
        ):
            _raise_adapter_error(
                "Attested research pipeline execution identity drifted",
                reason="attested_pipeline_execution_drift",
                expected_execution_hash=expected_execution_hash,
                actual_execution_hash=actual_hash,
            )
        evidence_stage_indexes = _selection_evidence_stage_indexes(stages)
        if (
            vars(self._pipeline).get("_evidence_sink") is not self._evidence_sink
            or evidence_stage_indexes != self._evidence_stage_indexes
            or any(
                getattr(stages[index], "evidence_sink", object())
                is not self._evidence_sink
                for index in evidence_stage_indexes
            )
        ):
            _raise_adapter_error(
                "Attested research pipeline selection evidence sink drifted",
                reason="attested_pipeline_evidence_sink_drift",
            )
        return self._pipeline


def _seal_attested_pipeline(
    *,
    pipeline: StrategyPipeline,
    compiled: CompiledNodePipeline,
) -> AttestedNodePipeline:
    stages = pipeline.stages
    execution_hash = _pipeline_execution_hash(compiled, stages)
    evidence_sink = vars(pipeline).get("_evidence_sink")
    attested = object.__new__(AttestedNodePipeline)
    object.__setattr__(attested, "_pipeline", pipeline)
    object.__setattr__(attested, "_compiled", compiled)
    object.__setattr__(attested, "_execution_hash", execution_hash)
    object.__setattr__(attested, "_evidence_sink", evidence_sink)
    object.__setattr__(
        attested,
        "_evidence_stage_indexes",
        _selection_evidence_stage_indexes(stages),
    )
    return attested


def _selection_evidence_stage_indexes(
    stages: Sequence[DecisionStage],
) -> tuple[int, ...]:
    """Locate only stages whose declared state includes the shared evidence sink."""
    indexes: list[int] = []
    for index, stage in enumerate(stages):
        declares_sink = (
            is_dataclass(stage)
            and not isinstance(stage, type)
            and any(item.name == "evidence_sink" for item in fields(stage))
        )
        if not declares_sink:
            try:
                declares_sink = "evidence_sink" in vars(stage)
            except TypeError:
                declares_sink = False
        if declares_sink:
            indexes.append(index)
    return tuple(indexes)


def _bind_selection_evidence_sink(
    stage: DecisionStage,
    evidence_sink: SelectionEvidenceSink | None,
) -> DecisionStage:
    """Bind caller-owned evidence to every dataclass stage that declares it."""
    if (
        is_dataclass(stage)
        and not isinstance(stage, type)
        and any(item.name == "evidence_sink" for item in fields(stage))
    ):
        return cast("DecisionStage", replace(stage, evidence_sink=evidence_sink))
    return stage


def _state_type(value: object) -> str:
    return f"{type(value).__module__}:{type(value).__qualname__}"


def _canonical_execution_state(
    value: object,
    *,
    path: str,
    ancestors: frozenset[int] = frozenset(),
) -> object:
    """Serialize deterministic builtin stage state; reject opaque executables."""
    scalar = _canonical_scalar_execution_state(
        value,
        path=path,
        ancestors=ancestors,
    )
    if scalar is not _UNRESOLVED_EXECUTION_STATE:
        return scalar

    value_id = id(value)
    if value_id in ancestors:
        _raise_adapter_error(
            "Pipeline stage state must be acyclic",
            reason="invalid_pipeline_stage_state",
            path=path,
        )
    nested_ancestors = ancestors | {value_id}
    container = _canonical_container_execution_state(
        value,
        path=path,
        ancestors=nested_ancestors,
    )
    if container is not _UNRESOLVED_EXECUTION_STATE:
        return container
    return _canonical_object_execution_state(
        value,
        path=path,
        ancestors=nested_ancestors,
    )


def _canonical_scalar_execution_state(
    value: object,
    *,
    path: str,
    ancestors: frozenset[int],
) -> object:
    result: object = _UNRESOLVED_EXECUTION_STATE
    if value is None or type(value) in {bool, int, str}:
        result = value
    elif type(value) is float:
        if not isfinite(value):
            _raise_adapter_error(
                "Pipeline stage state must be finite",
                reason="invalid_pipeline_stage_state",
                path=path,
            )
        result = value
    elif type(value) is bytes:
        result = {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    elif isinstance(value, Decimal):
        result = {"decimal": str(value)}
    elif isinstance(value, datetime):
        result = {"datetime": value.isoformat()}
    elif isinstance(value, date):
        result = {"date": value.isoformat()}
    elif isinstance(value, Enum):
        result = {
            "type": _state_type(value),
            "value": _canonical_execution_state(
                value.value,
                path=f"{path}.value",
                ancestors=ancestors,
            ),
        }
    return result


def _canonical_container_execution_state(
    value: object,
    *,
    path: str,
    ancestors: frozenset[int],
) -> object:
    result: object = _UNRESOLVED_EXECUTION_STATE
    if isinstance(value, Mapping):
        entries: list[tuple[str, object]] = []
        for raw_key, item in cast("Mapping[object, object]", value).items():
            if type(raw_key) is not str:
                _raise_adapter_error(
                    "Pipeline stage mappings require string keys",
                    reason="invalid_pipeline_stage_state",
                    path=path,
                )
            entries.append((raw_key, item))
        result = {
            key: _canonical_execution_state(
                item,
                path=f"{path}.{key}",
                ancestors=ancestors,
            )
            for key, item in sorted(entries)
        }
    elif isinstance(value, tuple | list):
        sequence = cast("Sequence[object]", value)
        result = [
            _canonical_execution_state(
                item,
                path=f"{path}[{index}]",
                ancestors=ancestors,
            )
            for index, item in enumerate(sequence)
        ]
    elif isinstance(value, set | frozenset):
        unordered = cast("set[object] | frozenset[object]", value)
        items = [
            _canonical_execution_state(
                item,
                path=f"{path}[]",
                ancestors=ancestors,
            )
            for item in unordered
        ]
        result = sorted(
            items, key=lambda item: orjson.dumps(item, option=orjson.OPT_SORT_KEYS)
        )
    return result


def _canonical_object_execution_state(
    value: object,
    *,
    path: str,
    ancestors: frozenset[int],
) -> object:
    """Canonicalize approved Ditto dataclass/object internals."""
    state: dict[str, object]
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_fields = fields(value)
        field_names = frozenset(field.name for field in dataclass_fields)
        if hasattr(value, "__dict__"):
            unexpected_fields = tuple(sorted(vars(value).keys() - field_names))
            if unexpected_fields:
                _raise_adapter_error(
                    "Pipeline dataclass state contains undeclared fields",
                    reason="invalid_pipeline_stage_state",
                    path=path,
                    unexpected_fields=unexpected_fields,
                )
        state = {
            field.name: getattr(value, field.name)
            for field in dataclass_fields
            if field.name != "evidence_sink"
        }
    elif _state_type(value).startswith("ditto_") and hasattr(value, "__dict__"):
        state = {
            key: item
            for key, item in vars(value).items()
            if key not in {"evidence_sink", "_evidence_sink"}
        }
    else:
        _raise_adapter_error(
            "Pipeline contains opaque executable state",
            reason="invalid_pipeline_stage_state",
            path=path,
            actual_type=_state_type(value),
        )
    return {
        "type": _state_type(value),
        "state": {
            key: _canonical_execution_state(
                item,
                path=f"{path}.{key}",
                ancestors=ancestors,
            )
            for key, item in sorted(state.items())
        },
    }


def _pipeline_execution_hash(
    compiled: CompiledNodePipeline,
    stages: Sequence[DecisionStage],
) -> str:
    """Bind resolved nodes and the concrete ordered stage implementations."""
    payload = {
        "schema_version": _PIPELINE_EXECUTION_SCHEMA_VERSION,
        "executor_contract": _PIPELINE_EXECUTOR_CONTRACT,
        "registry_manifest_hash": compiled.registry_manifest_hash,
        "required_datasets": list(compiled.required_datasets),
        "nodes": [
            {
                "node_id": node.node_id,
                "descriptor_identity": node.descriptor.identity,
                "implementation_key": node.implementation_key,
                "executor_contract_version": (
                    node.descriptor.executor_contract_version
                ),
                "config": canonical_json_value(
                    node.config,
                    field_name=f"compiled_node.{node.node_id}.config",
                ),
            }
            for node in compiled.nodes
        ],
        "stage_implementations": [
            f"{type(stage).__module__}:{type(stage).__qualname__}" for stage in stages
        ],
        "stage_execution_state": [
            _canonical_execution_state(stage, path=f"stages[{index}]")
            for index, stage in enumerate(stages)
        ],
    }
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def _raise_adapter_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {"reason": reason}
    payload.update(details)
    raise AppBuilderError(message, details=payload)


def _read_object(raw_value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(raw_value, Mapping):
        _raise_adapter_error(
            f"{field_name} must be an object",
            reason="invalid_legacy_node_config",
            field_name=field_name,
            actual_type=type(raw_value).__name__,
        )
    raw_mapping = cast("Mapping[object, object]", raw_value)
    result: dict[str, object] = {}
    for key, value in raw_mapping.items():
        if not isinstance(key, str):
            _raise_adapter_error(
                f"{field_name} keys must be strings",
                reason="invalid_legacy_node_config",
                field_name=field_name,
                actual_type=type(key).__name__,
            )
        result[key] = value
    return MappingProxyType(result)


def _read_required_config_value(
    config: Mapping[str, object],
    key: str,
    *,
    field_name: str,
) -> object:
    if key not in config:
        _raise_adapter_error(
            f"{field_name} is required",
            reason="missing_legacy_node_config",
            field_name=field_name,
        )
    return config[key]


def _read_constraints(raw_value: object) -> tuple[ConstraintSpec, ...]:
    items = as_sequence(raw_value, field_name="allocator.constraints")
    constraints: list[ConstraintSpec] = []
    for index, item in enumerate(items):
        field_name = f"allocator.constraints[{index}]"
        config = _read_object(item, field_name=field_name)
        params = _read_object(
            config.get("params", {}),
            field_name=f"{field_name}.params",
        )
        constraints.append(
            ConstraintSpec(
                type=read_str_value(
                    _read_required_config_value(
                        config,
                        "type",
                        field_name=f"{field_name}.type",
                    ),
                    field_name=f"{field_name}.type",
                ),
                params=cast("dict[str, object]", params),
                priority=read_int(
                    config.get("priority", 100),
                    field_name=f"{field_name}.priority",
                ),
            ),
        )
    return tuple(constraints)


def _read_impact_model(raw_value: object) -> ImpactModel:
    field_name = "execution.cost_model.impact_model"
    value = read_str_value(raw_value, field_name=field_name)
    try:
        return ImpactModel(value)
    except ValueError as exc:
        raise AppBuilderError(
            f"unsupported {field_name}: {value}",
            details={
                "reason": "invalid_legacy_node_config",
                "field_name": field_name,
                "actual_value": value,
            },
        ) from exc


def _read_order_type(raw_value: object) -> OrderType:
    field_name = "execution.default_order_type"
    value = read_str_value(raw_value, field_name=field_name)
    try:
        return OrderType(value)
    except ValueError as exc:
        raise AppBuilderError(
            f"unsupported {field_name}: {value}",
            details={
                "reason": "invalid_legacy_node_config",
                "field_name": field_name,
                "actual_value": value,
            },
        ) from exc


def _compiled_legacy_configs(
    nodes: tuple[CompiledNode, ...],
) -> Mapping[str, Mapping[str, object]]:
    configs: dict[str, Mapping[str, object]] = {}
    duplicates: list[str] = []
    for node in nodes:
        key = node.implementation_key
        if key not in _LEGACY_IMPLEMENTATION_KEYS:
            continue
        if key in configs:
            duplicates.append(key)
        configs[key] = node.config
    missing = tuple(sorted(_LEGACY_IMPLEMENTATION_KEYS - configs.keys()))
    if missing or duplicates:
        _raise_adapter_error(
            "compiled pipeline has an invalid legacy adapter shape",
            reason="invalid_legacy_adapter_shape",
            missing_implementation_keys=missing,
            duplicate_implementation_keys=tuple(sorted(duplicates)),
        )
    return MappingProxyType(configs)


def _build_legacy_runtime_view(
    base_spec: StrategySpec,
    nodes: tuple[CompiledNode, ...],
) -> _LegacyRuntimeView:
    """从全部 compiled legacy configs 重建 factory 的唯一事实源。"""
    configs = _compiled_legacy_configs(nodes)
    universe = configs["legacy.universe.v1"]
    factor = configs["legacy.factor_set.v1"]
    scorer = configs["legacy.scorer.v1"]
    selector = configs["legacy.selector.v1"]
    allocator = configs["legacy.allocator.v1"]
    execution = configs["legacy.execution_assumption.v1"]
    validation = configs["legacy.validation.v1"]

    params = _read_object(factor["params"], field_name="factor_set.params")
    scorer_params = _read_object(scorer["params"], field_name="scorer.params")
    selector_params = _read_object(selector["params"], field_name="selector.params")
    cost_model_config = _read_object(
        execution["cost_model"],
        field_name="execution.cost_model",
    )
    cost_defaults = CostModelSpec()
    cost_model = CostModelSpec(
        commission_rate=read_float(
            cost_model_config.get(
                "commission_rate",
                cost_defaults.commission_rate,
            ),
            field_name="execution.cost_model.commission_rate",
        ),
        slippage_bps=read_float(
            cost_model_config.get("slippage_bps", cost_defaults.slippage_bps),
            field_name="execution.cost_model.slippage_bps",
        ),
        impact_model=_read_impact_model(
            cost_model_config.get("impact_model", cost_defaults.impact_model),
        ),
    )
    effective_spec = replace(
        base_spec,
        template=read_str_value(factor["template"], field_name="factor_set.template"),
        universe=read_str_value(universe["universe"], field_name="universe.universe"),
        asset_class=read_str_value(
            universe["asset_class"],
            field_name="universe.asset_class",
        ),
        benchmark=read_optional_str(
            universe["benchmark"],
            field_name="universe.benchmark",
        ),
        params=cast("dict[str, object]", params),
        scorer=ScorerSpec(
            method=read_str_value(scorer["method"], field_name="scorer.method"),
            params=cast("dict[str, object]", scorer_params),
        ),
        selector=SelectorSpec(
            method=read_str_value(selector["method"], field_name="selector.method"),
            params=cast("dict[str, object]", selector_params),
        ),
        constraints=_read_constraints(allocator["constraints"]),
        execution=ExecutionSpec(
            frequency=read_str_value(
                execution["frequency"],
                field_name="execution.frequency",
            ),
            method=read_str_value(
                execution["method"],
                field_name="execution.method",
            ),
            cost_model=cost_model,
            default_order_type=_read_order_type(execution["default_order_type"]),
        ),
        signal_expressions=as_str_tuple(
            factor["signal_expressions"],
            field_name="factor_set.signal_expressions",
        ),
        signal_weights=as_float_tuple(
            factor["signal_weights"],
            field_name="factor_set.signal_weights",
        ),
        required_datasets=as_str_tuple(
            factor["required_datasets"],
            field_name="factor_set.required_datasets",
        ),
    )
    read_str_value(
        validation["legacy_contract"],
        field_name="validation.legacy_contract",
    )
    metadata_configs = MappingProxyType(
        {key: configs[key] for key in sorted(_LEGACY_METADATA_IMPLEMENTATION_KEYS)},
    )
    return _LegacyRuntimeView(
        spec=effective_spec,
        metadata_configs=metadata_configs,
    )


def _build_trend_filter(
    config: Mapping[str, object],
    *,
    evidence_sink: SelectionEvidenceSink | None,
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
            evidence_sink=evidence_sink,
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
        factor_bindings: tuple[FactorScoreColumnBinding, ...] = (),
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> StrategyPipeline:
        """经 compiler 和 versioned legacy adapter 构造唯一现有 runner。"""
        return NodePipelineBuilder.build_attested(
            self,
            legacy_spec=legacy_spec,
            pipeline=pipeline,
            strategy_kind=strategy_kind,
            factor_bindings=factor_bindings,
            evidence_sink=evidence_sink,
        ).pipeline

    def build_attested(
        self,
        *,
        legacy_spec: StrategySpec,
        pipeline: PipelineSpec,
        strategy_kind: StrategyKind,
        factor_bindings: tuple[FactorScoreColumnBinding, ...] = (),
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> AttestedNodePipeline:
        """Build once and bind the actual ordered stage implementations."""
        compiled = compile_node_pipeline(
            pipeline,
            registry=self._registry,
            strategy_kind=strategy_kind,
        )
        for node in compiled.nodes:
            if node.implementation_key not in _SUPPORTED_IMPLEMENTATION_KEYS:
                NodePipelineBuilder._raise_unknown_implementation(node)
        runtime_view = _build_legacy_runtime_view(legacy_spec, compiled.nodes)
        legacy_groups = build_legacy_node_stage_groups(
            runtime_view.spec,
            factor_bindings=factor_bindings,
            evidence_sink=evidence_sink,
        )
        stages: list[DecisionStage] = []
        for node in compiled.nodes:
            resolved = NodePipelineBuilder._resolve_builtin_stages(
                node,
                legacy_groups=legacy_groups,
                metadata_configs=runtime_view.metadata_configs,
                evidence_sink=evidence_sink,
            )
            stages.extend(
                _bind_selection_evidence_sink(stage, evidence_sink)
                for stage in resolved
            )
        return _seal_attested_pipeline(
            pipeline=StrategyPipeline(stages, evidence_sink=evidence_sink),
            compiled=compiled,
        )

    @staticmethod
    def _resolve_builtin_stages(
        node: CompiledNode,
        *,
        legacy_groups: Mapping[str, Sequence[DecisionStage]],
        metadata_configs: Mapping[str, Mapping[str, object]],
        evidence_sink: SelectionEvidenceSink | None,
    ) -> Sequence[DecisionStage]:
        implementation_key = node.implementation_key
        legacy_stages = legacy_groups.get(implementation_key)
        if legacy_stages is not None:
            return legacy_stages
        if implementation_key in metadata_configs:
            return ()
        if implementation_key == "builtin.trend_filter.v1":
            return _build_trend_filter(
                node.config,
                evidence_sink=evidence_sink,
            )
        NodePipelineBuilder._raise_unknown_implementation(node)

    @staticmethod
    def _raise_unknown_implementation(node: CompiledNode) -> NoReturn:
        implementation_key = node.implementation_key
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
