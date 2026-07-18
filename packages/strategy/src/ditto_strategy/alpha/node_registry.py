"""R3 内置 ``NodeDescriptor`` 注册表与稳定 manifest identity。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import NoReturn, cast

import orjson

from ditto_strategy.alpha._canonical_values import freeze_json_mapping
from ditto_strategy.alpha.nodes import NodeCategory, NodeRef
from ditto_strategy.alpha.specs import StrategyKind
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "NodeConfigType",
    "NodeDescriptor",
    "NodeRegistry",
    "default_node_registry",
]

_BUILTIN_ORIGIN = "builtin"


def _empty_config_schema() -> dict[str, NodeConfigType]:
    return {}


def _empty_json_mapping() -> dict[str, object]:
    return {}


class NodeConfigType(StrEnum):
    """Descriptor config schema 支持的固定 JSON 类型。"""

    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    STRING_ARRAY = "string_array"
    NUMBER_ARRAY = "number_array"
    OBJECT_ARRAY = "object_array"
    STRING_OR_NULL = "string_or_null"
    JSON = "json"


def _raise_registry_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {"reason": reason}
    payload.update(details)
    raise StrategySpecError(message, details=payload)


def _require_non_empty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_registry_error(
            f"NodeDescriptor.{field_name} must be non-empty",
            reason="invalid_descriptor_field",
            field_name=field_name,
            actual_value=value,
        )
    return value


def _require_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        _raise_registry_error(
            f"NodeDescriptor.{field_name} must be tuple[str, ...]",
            reason="invalid_descriptor_field",
            field_name=field_name,
        )
    items = cast("tuple[object, ...]", value)
    if not all(isinstance(item, str) and item.strip() for item in items):
        _raise_registry_error(
            f"NodeDescriptor.{field_name} must be tuple[str, ...]",
            reason="invalid_descriptor_field",
            field_name=field_name,
        )
    return tuple(sorted({cast(str, item) for item in items}))


def _require_strategy_kind_tuple(value: object) -> tuple[StrategyKind, ...]:
    if not isinstance(value, tuple):
        _raise_registry_error(
            "NodeDescriptor.supported_strategy_kinds must be non-empty",
            reason="invalid_descriptor_field",
            field_name="supported_strategy_kinds",
        )
    items = cast("tuple[object, ...]", value)
    if not items or not all(isinstance(item, StrategyKind) for item in items):
        _raise_registry_error(
            "NodeDescriptor.supported_strategy_kinds must be non-empty",
            reason="invalid_descriptor_field",
            field_name="supported_strategy_kinds",
        )
    return tuple(
        sorted(
            {cast(StrategyKind, item) for item in items},
            key=lambda item: item.value,
        ),
    )


def _freeze_config_schema(
    value: object,
) -> Mapping[str, NodeConfigType]:
    if not isinstance(value, Mapping):
        _raise_registry_error(
            "NodeDescriptor.config_schema must be a mapping",
            reason="invalid_config_schema",
            field_name="config_schema",
        )
    schema: dict[str, NodeConfigType] = {}
    raw_schema = cast("Mapping[object, object]", value)
    for key, item in raw_schema.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(
                item,
                NodeConfigType,
            )
        ):
            _raise_registry_error(
                "NodeDescriptor.config_schema contains an invalid field",
                reason="invalid_config_schema",
                field_name="config_schema",
                config_key=key,
            )
        schema[key] = item
    return MappingProxyType(schema)


def _matches_config_type(value: object, expected: NodeConfigType) -> bool:
    if expected is NodeConfigType.JSON:
        return True
    scalar_types: dict[NodeConfigType, type | tuple[type, ...]] = {
        NodeConfigType.STRING: str,
        NodeConfigType.STRING_OR_NULL: (str, type(None)),
        NodeConfigType.BOOLEAN: bool,
        NodeConfigType.INTEGER: int,
        NodeConfigType.NUMBER: (int, float),
        NodeConfigType.OBJECT: Mapping,
    }
    scalar_type = scalar_types.get(expected)
    if scalar_type is not None:
        matches = isinstance(value, scalar_type)
        return matches and not (
            expected in {NodeConfigType.INTEGER, NodeConfigType.NUMBER}
            and isinstance(value, bool)
        )
    if not isinstance(value, tuple):
        return False
    items = cast("tuple[object, ...]", value)
    if expected is NodeConfigType.OBJECT_ARRAY:
        return all(isinstance(item, Mapping) for item in items)
    item_types = {
        NodeConfigType.STRING_ARRAY: str,
        NodeConfigType.NUMBER_ARRAY: (int, float),
    }
    item_type = item_types.get(expected)
    return item_type is not None and all(
        isinstance(item, item_type)
        and not (expected is NodeConfigType.NUMBER_ARRAY and isinstance(item, bool))
        for item in items
    )


def _validate_resolved_config(
    descriptor: NodeDescriptor,
    config: Mapping[str, object],
    *,
    require_complete: bool,
) -> None:
    unknown_keys = tuple(sorted(set(config) - set(descriptor.config_schema)))
    if unknown_keys:
        _raise_registry_error(
            f"Node config contains unknown fields for {descriptor.identity}",
            reason="unknown_node_config_field",
            node_identity=descriptor.identity,
            unknown_fields=unknown_keys,
        )
    missing_keys = tuple(sorted(set(descriptor.config_schema) - set(config)))
    if require_complete and missing_keys:
        _raise_registry_error(
            f"Node config is missing required fields for {descriptor.identity}",
            reason="missing_node_config_field",
            node_identity=descriptor.identity,
            missing_fields=missing_keys,
        )
    for key, actual in config.items():
        expected = descriptor.config_schema[key]
        if not _matches_config_type(actual, expected):
            _raise_registry_error(
                f"Node config field {key!r} has the wrong type",
                reason="invalid_node_config_type",
                node_identity=descriptor.identity,
                config_key=key,
                expected_type=expected.value,
                actual_type=type(actual).__name__,
            )


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {str(key): _plain_json(item) for key, item in mapping.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in cast("tuple[object, ...]", value)]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _validate_manifest_value(value: object, *, field_name: str) -> None:
    """在 registry 编码前定位 orjson 不支持的整数路径。"""
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            _validate_manifest_value(
                item,
                field_name=f"{field_name}.{key}",
            )
        return
    if isinstance(value, list):
        items = cast("list[object]", value)
        for index, item in enumerate(items):
            _validate_manifest_value(
                item,
                field_name=f"{field_name}[{index}]",
            )
        return
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            orjson.dumps(value)
        except (TypeError, ValueError, OverflowError):
            _raise_registry_error(
                "Node descriptor manifest contains an unsupported integer",
                reason="invalid_descriptor_manifest_value",
                field_name=field_name,
                actual_type="int",
            )


def _validate_descriptor_category(value: object) -> None:
    if not isinstance(value, NodeCategory):
        _raise_registry_error(
            "NodeDescriptor.category must be a NodeCategory",
            reason="invalid_descriptor_field",
            field_name="category",
        )


def _validate_descriptor_deterministic(value: object) -> None:
    if not isinstance(value, bool):
        _raise_registry_error(
            "NodeDescriptor.deterministic must be bool",
            reason="invalid_descriptor_field",
            field_name="deterministic",
        )


def _require_node_ref(value: object) -> NodeRef:
    if not isinstance(value, NodeRef):
        _raise_registry_error(
            "NodeRegistry.lookup requires a NodeRef",
            reason="invalid_node_ref",
        )
    return value


@dataclass(frozen=True)
class NodeDescriptor:
    """一个可版本化、可哈希且不携带 Python callable 的节点契约。"""

    node_type: str
    version: str
    category: NodeCategory
    display_name: str
    input_contract: str
    output_contract: str
    config_schema: Mapping[str, NodeConfigType] = field(
        default_factory=_empty_config_schema,
    )
    default_config: Mapping[str, object] = field(
        default_factory=_empty_json_mapping,
    )
    required_datasets: tuple[str, ...] = ()
    capability_tags: tuple[str, ...] = ()
    supported_strategy_kinds: tuple[StrategyKind, ...] = (
        StrategyKind.STOCK_SELECTION,
        StrategyKind.ETF_ROTATION,
    )
    deterministic: bool = True
    implementation_key: str = ""
    executor_contract_version: str = "1"
    origin: str = _BUILTIN_ORIGIN

    def __post_init__(self) -> None:
        """冻结 descriptor 的全部 identity 字段并验证 schema/default。"""
        NodeRef(self.node_type, self.version)
        _validate_descriptor_category(self.category)
        for field_name in (
            "display_name",
            "input_contract",
            "output_contract",
            "implementation_key",
            "executor_contract_version",
            "origin",
        ):
            _require_non_empty_string(getattr(self, field_name), field_name=field_name)
        _validate_descriptor_deterministic(self.deterministic)
        schema = _freeze_config_schema(self.config_schema)
        default_config = freeze_json_mapping(
            self.default_config,
            field_name="default_config",
        )
        object.__setattr__(self, "config_schema", schema)
        object.__setattr__(self, "default_config", default_config)
        object.__setattr__(
            self,
            "required_datasets",
            _require_string_tuple(
                self.required_datasets,
                field_name="required_datasets",
            ),
        )
        object.__setattr__(
            self,
            "capability_tags",
            _require_string_tuple(
                self.capability_tags,
                field_name="capability_tags",
            ),
        )
        object.__setattr__(
            self,
            "supported_strategy_kinds",
            _require_strategy_kind_tuple(self.supported_strategy_kinds),
        )
        _validate_resolved_config(
            self,
            default_config,
            require_complete=False,
        )

    @property
    def ref(self) -> NodeRef:
        """返回 descriptor 的稳定节点引用。"""
        return NodeRef(self.node_type, self.version)

    @property
    def identity(self) -> str:
        """返回 ``node_type@version`` identity。"""
        return self.ref.identity

    def resolve_config(
        self,
        config: Mapping[str, object],
    ) -> Mapping[str, object]:
        """应用 default 后按固定 schema 校验并返回不可变快照。"""
        resolved = {**self.default_config, **config}
        frozen = freeze_json_mapping(
            resolved,
            field_name=f"node_config.{self.identity}",
        )
        _validate_resolved_config(
            self,
            frozen,
            require_complete=True,
        )
        return frozen

    def manifest_payload(self) -> dict[str, object]:
        """返回执行 identity；有意排除 display_name。"""
        return {
            "capability_tags": list(self.capability_tags),
            "category": self.category.value,
            "config_schema": {
                key: value.value for key, value in sorted(self.config_schema.items())
            },
            "default_config": _plain_json(self.default_config),
            "deterministic": self.deterministic,
            "executor_contract_version": self.executor_contract_version,
            "implementation_key": self.implementation_key,
            "input_contract": self.input_contract,
            "node_type": self.node_type,
            "origin": self.origin,
            "output_contract": self.output_contract,
            "required_datasets": list(self.required_datasets),
            "supported_strategy_kinds": [
                kind.value for kind in self.supported_strategy_kinds
            ],
            "version": self.version,
        }


class NodeRegistry:
    """只读内置 descriptor registry；R3 不做动态发现或 import。"""

    def __init__(self, descriptors: Sequence[object]) -> None:
        raw_descriptors = tuple(descriptors)
        if not all(isinstance(item, NodeDescriptor) for item in raw_descriptors):
            _raise_registry_error(
                "NodeRegistry accepts only NodeDescriptor values",
                reason="invalid_descriptor_value",
            )
        resolved = tuple(cast(NodeDescriptor, item) for item in raw_descriptors)
        non_builtin = tuple(
            descriptor.identity
            for descriptor in resolved
            if descriptor.origin != _BUILTIN_ORIGIN
        )
        if non_builtin:
            _raise_registry_error(
                "R3 NodeRegistry accepts builtin descriptors only",
                reason="non_builtin_descriptor_origin",
                node_identities=non_builtin,
            )
        identities = tuple(descriptor.identity for descriptor in resolved)
        if len(set(identities)) != len(identities):
            _raise_registry_error(
                "NodeRegistry descriptor identities must be unique",
                reason="duplicate_descriptor_identity",
                node_identities=identities,
            )
        self._descriptors = tuple(sorted(resolved, key=lambda item: item.identity))
        self._by_identity = MappingProxyType(
            {descriptor.identity: descriptor for descriptor in self._descriptors},
        )
        manifest_payloads: list[dict[str, object]] = []
        for descriptor in self._descriptors:
            payload = descriptor.manifest_payload()
            _validate_manifest_value(
                payload,
                field_name=f"descriptors.{descriptor.identity}",
            )
            manifest_payloads.append(payload)
        try:
            manifest_bytes = orjson.dumps(
                manifest_payloads,
                option=orjson.OPT_SORT_KEYS,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise StrategySpecError(
                "Node registry manifest has no canonical JSON identity",
                details={
                    "reason": "invalid_descriptor_manifest_value",
                    "field_name": "descriptors",
                },
            ) from exc
        self._manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()

    @property
    def descriptors(self) -> tuple[NodeDescriptor, ...]:
        """返回 identity 排序后的 frozen manifest entries。"""
        return self._descriptors

    @property
    def manifest_hash(self) -> str:
        """返回完整 64 位 SHA-256 manifest identity。"""
        return self._manifest_hash

    def lookup(self, ref: NodeRef) -> NodeDescriptor:
        """按 exact ``node_type@version`` 查询；未知 identity fail closed。"""
        ref_value = _require_node_ref(ref)
        descriptor = self._by_identity.get(ref_value.identity)
        if descriptor is None:
            _raise_registry_error(
                f"unknown node descriptor: {ref_value.identity}",
                reason="unknown_node_descriptor",
                node_identity=ref_value.identity,
            )
        return descriptor


def _descriptor(
    node_type: str,
    category: NodeCategory,
    input_contract: str,
    output_contract: str,
    implementation_key: str,
    *,
    config_schema: Mapping[str, NodeConfigType] | None = None,
    default_config: Mapping[str, object] | None = None,
) -> NodeDescriptor:
    return NodeDescriptor(
        node_type=node_type,
        version="1",
        category=category,
        display_name=category.value.replace("_", " ").title(),
        input_contract=input_contract,
        output_contract=output_contract,
        config_schema=config_schema or {},
        default_config=default_config or {},
        required_datasets=(),
        capability_tags=("r3.constrained",),
        supported_strategy_kinds=(
            StrategyKind.STOCK_SELECTION,
            StrategyKind.ETF_ROTATION,
        ),
        deterministic=True,
        implementation_key=implementation_key,
        executor_contract_version="1",
    )


def _legacy_descriptors() -> tuple[NodeDescriptor, ...]:
    """返回 Task1 legacy adapter 对应的内置过渡 descriptors。"""
    return (
        _descriptor(
            "legacy.universe",
            NodeCategory.UNIVERSE,
            "pipeline_input.v1",
            "universe_frame.v1",
            "legacy.universe.v1",
            config_schema={
                "asset_class": NodeConfigType.STRING,
                "benchmark": NodeConfigType.STRING_OR_NULL,
                "universe": NodeConfigType.STRING,
            },
            default_config={
                "asset_class": "",
                "benchmark": None,
                "universe": "",
            },
        ),
        _descriptor(
            "legacy.factor_set",
            NodeCategory.FACTOR_SET,
            "universe_frame.v1",
            "signal_frame.v1",
            "legacy.factor_set.v1",
            config_schema={
                "params": NodeConfigType.OBJECT,
                "required_datasets": NodeConfigType.STRING_ARRAY,
                "signal_expressions": NodeConfigType.STRING_ARRAY,
                "signal_weights": NodeConfigType.NUMBER_ARRAY,
                "template": NodeConfigType.STRING,
            },
            default_config={
                "params": {},
                "required_datasets": (),
                "signal_expressions": (),
                "signal_weights": (),
                "template": "",
            },
        ),
        _descriptor(
            "legacy.scorer",
            NodeCategory.SCORER,
            "signal_frame.v1",
            "score_frame.v1",
            "legacy.scorer.v1",
            config_schema={
                "method": NodeConfigType.STRING,
                "params": NodeConfigType.OBJECT,
            },
            default_config={"method": "rank", "params": {}},
        ),
        _descriptor(
            "legacy.selector",
            NodeCategory.SELECTOR,
            "score_frame.v1",
            "selected_frame.v1",
            "legacy.selector.v1",
            config_schema={
                "method": NodeConfigType.STRING,
                "params": NodeConfigType.OBJECT,
            },
            default_config={"method": "top_k", "params": {}},
        ),
        _descriptor(
            "legacy.allocator",
            NodeCategory.ALLOCATOR,
            "selected_frame.v1",
            "weighted_frame.v1",
            "legacy.allocator.v1",
            config_schema={"constraints": NodeConfigType.OBJECT_ARRAY},
            default_config={"constraints": ()},
        ),
        _descriptor(
            "legacy.execution_assumption",
            NodeCategory.EXECUTION_ASSUMPTION,
            "weighted_frame.v1",
            "execution_ready.v1",
            "legacy.execution_assumption.v1",
            config_schema={
                "cost_model": NodeConfigType.OBJECT,
                "default_order_type": NodeConfigType.STRING,
                "frequency": NodeConfigType.STRING,
                "method": NodeConfigType.STRING,
            },
            default_config={
                "cost_model": {},
                "default_order_type": "market",
                "frequency": "D",
                "method": "calendar",
            },
        ),
        _descriptor(
            "legacy.validation",
            NodeCategory.VALIDATION,
            "execution_ready.v1",
            "validated.v1",
            "legacy.validation.v1",
            config_schema={"legacy_contract": NodeConfigType.STRING},
            default_config={"legacy_contract": "strategy_spec_v1"},
        ),
        _descriptor(
            "builtin.trend_filter",
            NodeCategory.FILTER,
            "signal_frame.v1",
            "signal_frame.v1",
            "builtin.trend_filter.v1",
            config_schema={
                "direction": NodeConfigType.STRING,
                "signal_column": NodeConfigType.STRING,
                "threshold": NodeConfigType.NUMBER,
            },
            default_config={
                "direction": "long",
                "signal_column": "signal_value",
                "threshold": 0.0,
            },
        ),
    )


def default_node_registry() -> NodeRegistry:
    """构造确定性的 R3 builtin registry；无动态 discovery。"""
    return NodeRegistry(_legacy_descriptors())
