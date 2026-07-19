"""Typed StrategySpec v2 candidate parameter binding."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import NoReturn, cast

import orjson

from ditto_strategy.alpha._canonical_values import canonicalize_float_identity
from ditto_strategy.alpha._parameter_paths import (
    escape_parameter_path_segment,
    legacy_parameter_path,
)
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.nodes import NodeInstance, PipelineSpec
from ditto_strategy.alpha.spec_codec import canonical_spec_hash
from ditto_strategy.alpha.specs import ParamConstraint, StrategySpecV2
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "CandidateParameter",
    "EffectiveParameter",
    "ParameterBinder",
    "ParameterBindingResult",
    "ParameterDefinition",
    "ParameterSchema",
    "ParameterValue",
    "ParameterValueType",
    "canonical_parameter_hash",
    "escape_parameter_path_segment",
    "legacy_parameter_path",
]

type ParameterValue = bool | int | float | str

_MIN_PARAMETER_PATH_SEGMENTS = 5


class ParameterValueType(StrEnum):
    """Exact canonical scalar types accepted by candidate binding."""

    BOOLEAN = "bool"
    INTEGER = "int"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"


def _spec_invalid(
    message: str,
    *,
    reason: str,
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {
        "code": "SPEC_INVALID",
        "reason": reason,
    }
    payload.update(details)
    raise StrategySpecError(message, details=payload)


def _canonical_scalar(value: object, *, path: str) -> ParameterValue:
    if type(value) not in {bool, int, float, str}:
        _spec_invalid(
            "candidate parameter value must be a canonical scalar",
            reason="invalid_parameter_value",
            path=path,
            actual_type=type(value).__name__,
        )
    if isinstance(value, float):
        if not math.isfinite(value):
            _spec_invalid(
                "candidate parameter float must be finite",
                reason="invalid_parameter_value",
                path=path,
                actual_value=value,
            )
        return canonicalize_float_identity(value)
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            orjson.dumps(value)
        except (TypeError, ValueError, OverflowError):
            _spec_invalid(
                "candidate parameter integer has no canonical JSON identity",
                reason="invalid_parameter_value",
                path=path,
                actual_type="int",
            )
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _spec_invalid(
                "candidate parameter string has no canonical UTF-8 identity",
                reason="invalid_parameter_value",
                path=path,
                actual_type="str",
            )
    return cast(ParameterValue, value)


def _require_nonempty_path(
    value: object,
    *,
    message: str,
    location: str = "parameter.path",
) -> str:
    if not isinstance(value, str) or not value:
        _spec_invalid(
            message,
            reason="invalid_parameter_path",
            path=location,
            actual_type=type(value).__name__,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _spec_invalid(
            "parameter path has no canonical UTF-8 identity",
            reason="invalid_parameter_path",
            path=location,
            actual_type="str",
        )
    return value


@dataclass(frozen=True)
class CandidateParameter:
    """One typed candidate override received after transport parsing."""

    path: str
    value: ParameterValue

    def __post_init__(self) -> None:
        """Validate the canonical scalar at this transport boundary."""
        _require_nonempty_path(
            self.path,
            message="candidate parameter path must be non-empty",
            location="candidate_parameter.path",
        )
        object.__setattr__(
            self,
            "value",
            _canonical_scalar(self.value, path=self.path),
        )


@dataclass(frozen=True)
class EffectiveParameter:
    """One canonical path/value pair after baseline expansion and binding."""

    path: str
    value: ParameterValue

    def __post_init__(self) -> None:
        """Validate the expanded canonical path/value identity."""
        _require_nonempty_path(
            self.path,
            message="effective parameter path must be non-empty",
            location="effective_parameter.path",
        )
        object.__setattr__(
            self,
            "value",
            _canonical_scalar(self.value, path=self.path),
        )


def _unescape_parameter_path_segment(value: str, *, path: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "~":
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
            _spec_invalid(
                "parameter path contains an invalid RFC 6901 escape",
                reason="invalid_parameter_path",
                path=path,
            )
        result.append("~" if value[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _parse_parameter_path(path: str) -> tuple[str, tuple[str, ...]]:
    path = _require_nonempty_path(
        path,
        message="parameter schema names must be complete canonical paths",
        location="parameter_schema.path",
    )
    if not path.startswith("/"):
        _spec_invalid(
            "parameter schema names must be complete canonical paths",
            reason="invalid_parameter_path",
            path=path,
        )
    raw_segments = path.split("/")[1:]
    if len(raw_segments) < _MIN_PARAMETER_PATH_SEGMENTS:
        _spec_invalid(
            "parameter path is incomplete",
            reason="invalid_parameter_path",
            path=path,
        )
    segments = tuple(
        _unescape_parameter_path_segment(segment, path=path) for segment in raw_segments
    )
    if (
        segments[:2] != ("pipeline", "nodes")
        or segments[3] != "config"
        or not segments[2]
        or any(not segment for segment in segments[4:])
    ):
        _spec_invalid(
            "parameter path must target one node config leaf",
            reason="invalid_parameter_path",
            path=path,
        )
    canonical = "/" + "/".join(
        escape_parameter_path_segment(segment) for segment in segments
    )
    if canonical != path:
        _spec_invalid(
            "parameter path must use canonical RFC 6901 escaping",
            reason="invalid_parameter_path",
            path=path,
            canonical_path=canonical,
        )
    return segments[2], segments[4:]


def _require_path_mapping(
    value: object,
    *,
    path: str,
    segment: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _spec_invalid(
            "parameter path target does not exist",
            reason="parameter_target_missing",
            path=path,
            missing_segment=segment,
        )
    return cast(Mapping[str, object], value)


def _read_mapping_leaf(
    mapping: Mapping[str, object],
    segments: tuple[str, ...],
    *,
    path: str,
) -> object:
    current: object = mapping
    for segment in segments:
        current_mapping = _require_path_mapping(
            current,
            path=path,
            segment=segment,
        )
        if segment not in current_mapping:
            _spec_invalid(
                "parameter path target does not exist",
                reason="parameter_target_missing",
                path=path,
                missing_segment=segment,
            )
        current = current_mapping[segment]
    return current


def _replace_mapping_leaf(
    mapping: Mapping[str, object],
    segments: tuple[str, ...],
    value: ParameterValue,
    *,
    path: str,
) -> dict[str, object]:
    segment = segments[0]
    if segment not in mapping:
        _spec_invalid(
            "parameter path target does not exist",
            reason="parameter_target_missing",
            path=path,
            missing_segment=segment,
        )
    result = dict(mapping)
    if len(segments) == 1:
        result[segment] = value
        return result
    child = mapping[segment]
    if not isinstance(child, Mapping):
        _spec_invalid(
            "parameter path crosses a non-object config value",
            reason="parameter_target_missing",
            path=path,
            missing_segment=segments[1],
        )
    result[segment] = _replace_mapping_leaf(
        cast("Mapping[str, object]", child),
        segments[1:],
        value,
        path=path,
    )
    return result


def _value_type(constraint: ParamConstraint) -> ParameterValueType:
    if constraint.dtype == "bool":
        return ParameterValueType.BOOLEAN
    if constraint.dtype == "int":
        return ParameterValueType.INTEGER
    if constraint.dtype == "float":
        return ParameterValueType.FLOAT
    if constraint.allowed_values:
        return ParameterValueType.ENUM
    return ParameterValueType.STRING


def _validate_constraint_shape(constraint: ParamConstraint) -> ParameterValueType:
    value_type = _value_type(constraint)
    numeric_values = (
        constraint.min_value,
        constraint.max_value,
        constraint.step,
    )
    if value_type in {
        ParameterValueType.BOOLEAN,
        ParameterValueType.STRING,
        ParameterValueType.ENUM,
    } and any(value is not None for value in numeric_values):
        _spec_invalid(
            "non-numeric parameter cannot declare numeric constraints",
            reason="invalid_parameter_constraints",
            path=constraint.name,
        )
    if value_type is not ParameterValueType.ENUM and constraint.allowed_values:
        _spec_invalid(
            "only string enum parameters can declare allowed_values",
            reason="invalid_parameter_enum",
            path=constraint.name,
        )
    if value_type is ParameterValueType.ENUM and len(
        set(constraint.allowed_values),
    ) != len(constraint.allowed_values):
        _spec_invalid(
            "parameter enum values must be unique",
            reason="invalid_parameter_enum",
            path=constraint.name,
        )
    if (
        constraint.min_value is not None
        and constraint.max_value is not None
        and constraint.min_value > constraint.max_value
    ):
        _spec_invalid(
            "parameter minimum cannot exceed maximum",
            reason="invalid_parameter_range",
            path=constraint.name,
        )
    if constraint.step is not None and constraint.step <= 0:
        _spec_invalid(
            "parameter step must be positive",
            reason="invalid_parameter_step",
            path=constraint.name,
        )
    if value_type is ParameterValueType.INTEGER and any(
        value is not None and not value.is_integer() for value in numeric_values
    ):
        _spec_invalid(
            "integer parameter constraints must be integral",
            reason="invalid_parameter_step",
            path=constraint.name,
        )
    return value_type


def _matches_value_type(value: object, value_type: ParameterValueType) -> bool:
    if value_type is ParameterValueType.BOOLEAN:
        return type(value) is bool
    if value_type is ParameterValueType.INTEGER:
        return type(value) is int
    if value_type is ParameterValueType.FLOAT:
        return type(value) is float
    return type(value) is str


def _is_decimal_step_aligned(
    value: float,
    *,
    origin: float | int,
    step: float,
) -> bool:
    """Compare decimal spellings as exact rational numbers, without context loss."""
    value_numerator, value_denominator = Decimal(str(value)).as_integer_ratio()
    origin_numerator, origin_denominator = Decimal(str(origin)).as_integer_ratio()
    step_numerator, step_denominator = Decimal(str(step)).as_integer_ratio()
    delta_numerator = (
        value_numerator * origin_denominator - origin_numerator * value_denominator
    )
    delta_denominator = value_denominator * origin_denominator
    quotient_numerator = delta_numerator * step_denominator
    quotient_denominator = delta_denominator * step_numerator
    return quotient_numerator % quotient_denominator == 0


@dataclass(frozen=True)
class ParameterDefinition:
    """One resolved schema entry bound to an exact node implementation."""

    path: str
    value_type: ParameterValueType
    node_id: str
    node_type: str
    node_version: str
    config_path: tuple[str, ...]
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    allowed_values: tuple[str, ...] = ()

    def validate_value(self, value: object) -> ParameterValue:
        """Validate one exact scalar candidate against this definition."""
        canonical = _canonical_scalar(value, path=self.path)
        if not _matches_value_type(canonical, self.value_type):
            _spec_invalid(
                "candidate parameter has the wrong exact scalar type",
                reason="parameter_type_mismatch",
                path=self.path,
                expected_type=self.value_type.value,
                actual_type=type(canonical).__name__,
            )
        if self.value_type is ParameterValueType.ENUM:
            enum_value = cast(str, canonical)
            if enum_value not in self.allowed_values:
                _spec_invalid(
                    "candidate parameter is not an allowed enum value",
                    reason="parameter_enum_mismatch",
                    path=self.path,
                    allowed_values=self.allowed_values,
                    actual_value=enum_value,
                )
            return canonical
        if self.value_type not in {
            ParameterValueType.INTEGER,
            ParameterValueType.FLOAT,
        }:
            return canonical
        is_integer = self.value_type is ParameterValueType.INTEGER
        numeric: int | float = (
            cast(int, canonical) if is_integer else cast(float, canonical)
        )
        minimum: int | float | None = (
            int(self.min_value)
            if is_integer and self.min_value is not None
            else self.min_value
        )
        maximum: int | float | None = (
            int(self.max_value)
            if is_integer and self.max_value is not None
            else self.max_value
        )
        if minimum is not None and numeric < minimum:
            _spec_invalid(
                "candidate parameter is below its minimum",
                reason="parameter_below_min",
                path=self.path,
                min_value=self.min_value,
                actual_value=canonical,
            )
        if maximum is not None and numeric > maximum:
            _spec_invalid(
                "candidate parameter is above its maximum",
                reason="parameter_above_max",
                path=self.path,
                max_value=self.max_value,
                actual_value=canonical,
            )
        if self.step is not None:
            origin: int | float = minimum if minimum is not None else 0
            if is_integer:
                aligned = (cast(int, numeric) - cast(int, origin)) % int(self.step) == 0
            else:
                aligned = _is_decimal_step_aligned(
                    cast(float, numeric),
                    origin=origin,
                    step=self.step,
                )
            if not aligned:
                _spec_invalid(
                    "candidate parameter does not align to its step",
                    reason="parameter_step_mismatch",
                    path=self.path,
                    step=self.step,
                    origin=origin,
                    actual_value=canonical,
                )
        return canonical


@dataclass(frozen=True)
class ParameterSchema:
    """A validated, exact-path parameter schema for one StrategySpec v2."""

    definitions: tuple[ParameterDefinition, ...]

    @classmethod
    def from_spec(
        cls,
        spec: StrategySpecV2,
        *,
        registry: NodeRegistry,
    ) -> ParameterSchema:
        """Resolve schema paths against exact nodes, versions, and config leaves."""
        spec = _require_strategy_spec_v2(spec)
        nodes_by_id = {node.node_id: node for node in spec.pipeline.nodes}
        definitions: list[ParameterDefinition] = []
        seen_paths: set[str] = set()
        for constraint in spec.parameter_schema:
            path = constraint.name
            if path in seen_paths:
                _spec_invalid(
                    "parameter schema paths must be unique",
                    reason="duplicate_parameter_path",
                    path=path,
                )
            seen_paths.add(path)
            node_id, config_path = _parse_parameter_path(path)
            node = nodes_by_id.get(node_id)
            if node is None:
                _spec_invalid(
                    "parameter path references an unknown node",
                    reason="parameter_target_missing",
                    path=path,
                    node_id=node_id,
                )
            try:
                descriptor = registry.lookup(node.ref)
            except StrategySpecError as exc:
                _spec_invalid(
                    "parameter path references an unknown node version",
                    reason="unknown_parameter_node_version",
                    path=path,
                    node_id=node_id,
                    node_type=node.ref.node_type,
                    node_version=node.ref.version,
                    registry_reason=exc.details.get("reason", ""),
                )
            if config_path[0] not in descriptor.config_schema:
                _spec_invalid(
                    "parameter path references an unknown node config field",
                    reason="parameter_target_missing",
                    path=path,
                    node_id=node_id,
                    missing_segment=config_path[0],
                )
            current_value = _read_mapping_leaf(
                node.config,
                config_path,
                path=path,
            )
            value_type = _validate_constraint_shape(constraint)
            definition = ParameterDefinition(
                path=path,
                value_type=value_type,
                node_id=node_id,
                node_type=node.ref.node_type,
                node_version=node.ref.version,
                config_path=config_path,
                min_value=constraint.min_value,
                max_value=constraint.max_value,
                step=constraint.step,
                allowed_values=constraint.allowed_values,
            )
            definition.validate_value(current_value)
            definitions.append(definition)
        return cls(definitions=tuple(sorted(definitions, key=lambda item: item.path)))

    def definition_for(self, path: str) -> ParameterDefinition | None:
        """Return an exact path match without aliases or fuzzy lookup."""
        return next(
            (definition for definition in self.definitions if definition.path == path),
            None,
        )


@dataclass(frozen=True)
class ParameterBindingResult:
    """Canonical identity and effective values for one bound candidate."""

    base_spec: StrategySpecV2
    resolved_spec: StrategySpecV2
    base_spec_hash: str
    resolved_spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]


def _require_strategy_spec_v2(value: object) -> StrategySpecV2:
    if not isinstance(value, StrategySpecV2):
        _spec_invalid(
            "parameter schema requires StrategySpecV2",
            reason="invalid_parameter_spec",
            path="spec",
            actual_type=type(value).__name__,
        )
    return value


def _require_candidate_parameters(
    value: object,
) -> tuple[CandidateParameter, ...]:
    if not isinstance(value, tuple):
        _spec_invalid(
            "candidate parameters must be tuple[CandidateParameter, ...]",
            reason="invalid_candidate_parameters",
            path="candidate_parameters",
            actual_type=type(value).__name__,
        )
    candidates: list[CandidateParameter] = []
    for index, item in enumerate(cast(tuple[object, ...], value)):
        if not isinstance(item, CandidateParameter):
            _spec_invalid(
                "candidate parameters must be tuple[CandidateParameter, ...]",
                reason="invalid_candidate_parameters",
                path=f"candidate_parameters[{index}]",
                actual_type=type(item).__name__,
            )
        path = _require_nonempty_path(
            item.path,
            message="candidate parameter path must be non-empty",
            location=f"candidate_parameters[{index}].path",
        )
        candidates.append(
            CandidateParameter(
                path=path,
                value=_canonical_scalar(item.value, path=path),
            ),
        )
    return tuple(candidates)


def canonical_parameter_hash(values: Sequence[EffectiveParameter]) -> str:
    """Return the canonical SHA-256 identity of complete effective values."""
    runtime_values = cast(object, values)
    if not isinstance(runtime_values, Sequence) or isinstance(
        runtime_values,
        (str, bytes, bytearray),
    ):
        _spec_invalid(
            "effective parameters must be a canonical sequence",
            reason="invalid_effective_parameters",
            path="effective_parameters",
            actual_type=type(runtime_values).__name__,
        )
    canonical_values: list[tuple[str, ParameterValue]] = []
    for index, item in enumerate(cast(Sequence[object], runtime_values)):
        if not isinstance(item, EffectiveParameter):
            _spec_invalid(
                "effective parameters must contain only EffectiveParameter values",
                reason="invalid_effective_parameters",
                path=f"effective_parameters[{index}]",
                actual_type=type(item).__name__,
            )
        path = _require_nonempty_path(
            item.path,
            message="effective parameter path must be non-empty",
            location=f"effective_parameters[{index}].path",
        )
        canonical_values.append(
            (path, _canonical_scalar(item.value, path=path)),
        )
    paths = [path for path, _ in canonical_values]
    if len(paths) != len(set(paths)):
        _spec_invalid(
            "effective parameter paths must be unique",
            reason="duplicate_effective_parameter",
            path="effective_parameters",
        )
    payload = [
        {"path": path, "value": value}
        for path, value in sorted(canonical_values, key=lambda item: item[0])
    ]
    try:
        encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    except (TypeError, ValueError, OverflowError) as exc:
        _spec_invalid(
            "effective parameters have no canonical JSON identity",
            reason="invalid_effective_parameters",
            path="effective_parameters",
            codec_error=type(exc).__name__,
        )
    return hashlib.sha256(encoded).hexdigest()


class ParameterBinder:
    """Apply typed candidates to a new immutable resolved StrategySpec v2."""

    def __init__(self, *, registry: NodeRegistry) -> None:
        self._registry = registry

    def bind(
        self,
        spec: StrategySpecV2,
        *,
        candidate_parameters: tuple[CandidateParameter, ...],
    ) -> ParameterBindingResult:
        """Validate and apply exact-path candidates without mutating ``spec``."""
        candidate_parameters = _require_candidate_parameters(candidate_parameters)
        schema = ParameterSchema.from_spec(spec, registry=self._registry)
        values_by_path: dict[str, ParameterValue] = {}
        for candidate in candidate_parameters:
            if candidate.path in values_by_path:
                _spec_invalid(
                    "candidate parameter paths must be unique",
                    reason="duplicate_parameter_binding",
                    path=candidate.path,
                )
            definition = schema.definition_for(candidate.path)
            if definition is None:
                _spec_invalid(
                    "candidate parameter path is not registered",
                    reason="unknown_parameter_path",
                    path=candidate.path,
                )
            values_by_path[candidate.path] = definition.validate_value(
                candidate.value,
            )

        nodes_by_id: dict[str, NodeInstance] = {
            node.node_id: node for node in spec.pipeline.nodes
        }
        for definition in schema.definitions:
            if definition.path not in values_by_path:
                continue
            node = nodes_by_id[definition.node_id]
            nodes_by_id[definition.node_id] = replace(
                node,
                config=_replace_mapping_leaf(
                    node.config,
                    definition.config_path,
                    values_by_path[definition.path],
                    path=definition.path,
                ),
            )
        resolved_pipeline = PipelineSpec(
            nodes=tuple(nodes_by_id[node.node_id] for node in spec.pipeline.nodes),
            sequence=spec.pipeline.sequence,
        )
        resolved_spec = replace(spec, pipeline=resolved_pipeline)
        resolved_nodes = {node.node_id: node for node in resolved_spec.pipeline.nodes}
        effective_parameters = tuple(
            EffectiveParameter(
                path=definition.path,
                value=definition.validate_value(
                    _read_mapping_leaf(
                        resolved_nodes[definition.node_id].config,
                        definition.config_path,
                        path=definition.path,
                    ),
                ),
            )
            for definition in schema.definitions
        )
        return ParameterBindingResult(
            base_spec=spec,
            resolved_spec=resolved_spec,
            base_spec_hash=canonical_spec_hash(spec),
            resolved_spec_hash=canonical_spec_hash(resolved_spec),
            parameter_hash=canonical_parameter_hash(effective_parameters),
            effective_parameters=effective_parameters,
        )
