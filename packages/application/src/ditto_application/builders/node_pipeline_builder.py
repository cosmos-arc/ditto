"""受约束节点编译结果到现有 ``StrategyPipeline`` 的 builtin 装配。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import NoReturn, cast

from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha.builtins.filtering import TrendFilterStage
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.nodes import PipelineSpec
from ditto_strategy.alpha.pipeline import (
    CompiledNode,
    StrategyPipeline,
    compile_node_pipeline,
)
from ditto_strategy.alpha.protocols import DecisionStage
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

__all__ = ["NodePipelineBuilder"]

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
        for node in compiled.nodes:
            if node.implementation_key not in _SUPPORTED_IMPLEMENTATION_KEYS:
                self._raise_unknown_implementation(node)
        runtime_view = _build_legacy_runtime_view(legacy_spec, compiled.nodes)
        legacy_groups = build_legacy_node_stage_groups(runtime_view.spec)
        stages: list[DecisionStage] = []
        for node in compiled.nodes:
            stages.extend(
                self._resolve_builtin_stages(
                    node,
                    legacy_groups=legacy_groups,
                    metadata_configs=runtime_view.metadata_configs,
                ),
            )
        return StrategyPipeline(stages)

    @staticmethod
    def _resolve_builtin_stages(
        node: CompiledNode,
        *,
        legacy_groups: Mapping[str, Sequence[DecisionStage]],
        metadata_configs: Mapping[str, Mapping[str, object]],
    ) -> Sequence[DecisionStage]:
        implementation_key = node.implementation_key
        legacy_stages = legacy_groups.get(implementation_key)
        if legacy_stages is not None:
            return legacy_stages
        if implementation_key in metadata_configs:
            return ()
        if implementation_key == "builtin.trend_filter.v1":
            return _build_trend_filter(node.config)
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
