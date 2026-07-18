"""StrategySpec v2 的类型化节点值对象与基础 sequence 约束。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn, TypeGuard

from ditto_strategy.alpha._canonical_values import freeze_json_mapping
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "NodeCategory",
    "NodeInstance",
    "NodeRef",
    "PipelineSpec",
]

_IDENTITY_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class NodeCategory(StrEnum):
    """受约束策略流水线的固定节点类别。"""

    UNIVERSE = "universe"
    FACTOR_SET = "factor_set"
    FILTER = "filter"
    SCORER = "scorer"
    SELECTOR = "selector"
    ALLOCATOR = "allocator"
    EXECUTION_ASSUMPTION = "execution_assumption"
    VALIDATION = "validation"


_CATEGORY_ORDER = {category: index for index, category in enumerate(NodeCategory)}


def _raise_node_error(
    message: str,
    *,
    field_name: str,
    reason: str,
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {"field_name": field_name, "reason": reason}
    payload.update(details)
    raise StrategySpecError(message, details=payload)


def _validate_identity_part(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTITY_PART_RE.fullmatch(value):
        _raise_node_error(
            f"NodeRef.{field_name} is invalid: {value!r}",
            field_name=field_name,
            reason="invalid_node_identity",
            actual_value=value,
        )


def _validate_node_id(value: object) -> None:
    if not isinstance(value, str) or not _NODE_ID_RE.fullmatch(value):
        _raise_node_error(
            f"NodeInstance.node_id is invalid: {value!r}",
            field_name="node_id",
            reason="invalid_node_id",
            actual_value=value,
        )


def _validate_node_ref(value: object) -> None:
    if not isinstance(value, NodeRef):
        _raise_node_error(
            "NodeInstance.ref must be a NodeRef",
            field_name="ref",
            reason="invalid_node_ref",
        )


def _validate_node_category(value: object) -> None:
    if not isinstance(value, NodeCategory):
        _raise_node_error(
            "NodeInstance.category must be a NodeCategory",
            field_name="category",
            reason="invalid_node_category",
            actual_value=value,
        )


def _validate_enabled(value: object) -> None:
    if not isinstance(value, bool):
        _raise_node_error(
            "NodeInstance.enabled must be bool",
            field_name="enabled",
            reason="invalid_enabled_flag",
            actual_value=value,
        )


def _validated_pipeline_nodes(
    value: object,
) -> tuple[NodeInstance, ...]:
    if not _is_object_tuple(value):
        _raise_node_error(
            "PipelineSpec.nodes must be a tuple",
            field_name="nodes",
            reason="invalid_nodes_container",
            actual_type=type(value).__name__,
        )
    if not all(isinstance(node, NodeInstance) for node in value):
        _raise_node_error(
            "PipelineSpec.nodes must contain only NodeInstance values",
            field_name="nodes",
            reason="invalid_node_value",
        )
    return tuple(node for node in value if isinstance(node, NodeInstance))


def _validated_pipeline_sequence(value: object) -> tuple[str, ...]:
    if not _is_object_tuple(value) or not all(
        isinstance(node_id, str) for node_id in value
    ):
        _raise_node_error(
            "PipelineSpec.sequence must be a tuple of node IDs",
            field_name="sequence",
            reason="invalid_sequence_container",
            actual_type=type(value).__name__,
        )
    return tuple(node_id for node_id in value if isinstance(node_id, str))


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


@dataclass(frozen=True)
class NodeRef:
    """稳定节点实现引用，identity 固定为 ``node_type@version``。"""

    node_type: str
    version: str

    def __post_init__(self) -> None:
        """拒绝空白或含分隔符歧义的 identity 组成部分。"""
        for field_name, value in (
            ("node_type", self.node_type),
            ("version", self.version),
        ):
            _validate_identity_part(value, field_name=field_name)

    @property
    def identity(self) -> str:
        """返回可持久化的稳定节点身份。"""
        return f"{self.node_type}@{self.version}"


@dataclass(frozen=True)
class NodeInstance:
    """流水线中的一个类型化节点实例。"""

    node_id: str
    ref: NodeRef
    category: NodeCategory
    config: Mapping[str, object] = field(default_factory=dict[str, object])
    enabled: bool = True

    def __post_init__(self) -> None:
        """校验节点实例的稳定 ID、引用与基础配置形态。"""
        _validate_node_id(self.node_id)
        _validate_node_ref(self.ref)
        _validate_node_category(self.category)
        _validate_enabled(self.enabled)
        object.__setattr__(
            self,
            "config",
            freeze_json_mapping(self.config, field_name="config"),
        )


@dataclass(frozen=True)
class PipelineSpec:
    """由显式 sequence 排序的节点集合，不表达自由 DAG edge。"""

    nodes: tuple[NodeInstance, ...]
    sequence: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 identity 完整性和类别单调顺序，不校验 cardinality。"""
        nodes = _validated_pipeline_nodes(self.nodes)
        sequence = _validated_pipeline_sequence(self.sequence)
        node_ids = tuple(node.node_id for node in nodes)
        if len(set(node_ids)) != len(node_ids):
            _raise_node_error(
                "PipelineSpec node_id values must be unique",
                field_name="node_id",
                reason="duplicate_node_id",
                node_ids=node_ids,
            )
        if len(set(sequence)) != len(sequence):
            _raise_node_error(
                "PipelineSpec.sequence must reference each node exactly once",
                field_name="sequence",
                reason="duplicate_sequence_node",
                sequence=sequence,
            )
        if len(sequence) != len(node_ids) or set(sequence) != set(node_ids):
            _raise_node_error(
                "PipelineSpec.sequence must reference every node exactly once",
                field_name="sequence",
                reason="sequence_node_mismatch",
                node_ids=node_ids,
                sequence=sequence,
            )

        nodes_by_id = {node.node_id: node for node in nodes}
        ordered_categories = tuple(
            nodes_by_id[node_id].category for node_id in sequence
        )
        category_positions = tuple(
            _CATEGORY_ORDER[category] for category in ordered_categories
        )
        if category_positions != tuple(sorted(category_positions)):
            _raise_node_error(
                "PipelineSpec.sequence has an invalid category order",
                field_name="sequence",
                reason="invalid_category_order",
                categories=tuple(category.value for category in ordered_categories),
            )
