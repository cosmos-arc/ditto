"""Immutable contracts for the governed R3 daily factor catalog."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import orjson

from ditto_features.expression.analyzer import analyze_expression
from ditto_features.expression.lexer import tokenize
from ditto_features.expression.parser import ExpressionParser
from ditto_features.factors.core_daily_validation import copy_sequence
from ditto_features.factors.spec import FactorSpec

__all__ = [
    "AssetLane",
    "AvailabilityReason",
    "CertifiedHistoryCoverage",
    "CoreFactorCatalog",
    "CoreFactorDescriptor",
    "CoreFactorSpecContract",
    "DatasetInputRequirement",
    "LaneDatasetRequirement",
    "Lookback",
    "LookbackUnit",
    "MaterializedIntermediate",
    "MissingValuePolicy",
    "PitRequirement",
    "PreprocessingContract",
    "PreprocessingStep",
    "StandardizationMethod",
    "WinsorizationMethod",
    "require_enum_member",
    "require_instance",
    "require_text",
]

_SHA256_HEX_LENGTH = 64


class AssetLane(StrEnum):
    """Supported R3 research lanes."""

    STOCK = "stock"
    ETF = "etf"


class LookbackUnit(StrEnum):
    """Unit attached to an input lookback."""

    TRADING_DAYS = "trading_days"
    REPORTING_PERIODS = "reporting_periods"


class PitRequirement(StrEnum):
    """Point-in-time alignment strength required before an input may run."""

    NONE = "none"
    KNOWN_AT = "known_at"
    ANNOUNCEMENT_KNOWN_AT = "announcement_known_at"


class PreprocessingStep(StrEnum):
    """Registered R3 preprocessing stages, in execution order."""

    PIT_ALIGNMENT = "pit_alignment"
    COVERAGE_VALIDATION = "coverage_validation"
    MISSING_VALUE_POLICY = "missing_value_policy"
    WINSORIZATION = "winsorization"
    NEUTRALIZATION = "neutralization"
    STANDARDIZATION = "standardization"
    WEIGHTED_SCORING = "weighted_scoring"


class MissingValuePolicy(StrEnum):
    """Supported missing-value behavior."""

    DROP = "drop"


class WinsorizationMethod(StrEnum):
    """Supported cross-sectional winsorization methods."""

    MAD_3 = "mad_3"


class StandardizationMethod(StrEnum):
    """Supported cross-sectional standardization methods."""

    ZSCORE = "zscore"


class AvailabilityReason(StrEnum):
    """Stable fail-closed reason codes for unavailable core factors."""

    LANE_UNSUPPORTED = "lane_unsupported"
    UNCERTIFIED_DATASET = "uncertified_dataset"
    INSUFFICIENT_HISTORY = "insufficient_history"
    BENCHMARK_MISSING = "benchmark_missing"
    BENCHMARK_UNCERTIFIED = "benchmark_uncertified"
    PIT_ALIGNMENT_MISSING = "pit_alignment_missing"
    PREPROCESSING_INPUT_MISSING = "preprocessing_input_missing"
    UNCERTIFIED_INPUT_FIELD = "uncertified_input_field"


def require_enum_member(
    value: object,
    enum_type: type[StrEnum],
    error_message: str,
) -> None:
    """Reject runtime values that are not members of the required enum."""
    if not isinstance(value, enum_type):
        raise ValueError(error_message)


def _require_non_negative_int(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("value must be a non-negative int")


def _require_positive_int(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("factor lookback must be a positive int")


def require_instance(
    value: object,
    expected_type: type[object],
    error_message: str,
) -> None:
    """Validate a runtime boundary even when its public annotation is narrower."""
    if not isinstance(value, expected_type):
        raise ValueError(error_message)


def require_text(value: object, field_name: str) -> None:
    """Reject empty or non-UTF-8 runtime text at a contract boundary."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} must be valid UTF-8") from exc


def _is_sha256_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class Lookback:
    """An explicit lookback with a non-ambiguous unit."""

    value: int
    unit: LookbackUnit

    def __post_init__(self) -> None:
        """Reject untyped, zero, and negative lookbacks."""
        _require_positive_int(self.value)
        require_enum_member(self.unit, LookbackUnit, "invalid lookback unit")


@dataclass(frozen=True, slots=True)
class CertifiedHistoryCoverage:
    """Certified history extents in every supported unit."""

    trading_days: int = 0
    reporting_periods: int = 0

    def __post_init__(self) -> None:
        """Reject negative or untyped coverage evidence."""
        for value in (self.trading_days, self.reporting_periods):
            _require_non_negative_int(value)

    def amount_for(self, unit: LookbackUnit) -> int:
        """Return certified coverage in the requested unit."""
        if unit is LookbackUnit.TRADING_DAYS:
            return self.trading_days
        if unit is LookbackUnit.REPORTING_PERIODS:
            return self.reporting_periods
        raise ValueError(f"unsupported lookback unit: {unit!r}")


@dataclass(frozen=True, slots=True)
class DatasetInputRequirement:
    """Certified fields, history, and PIT evidence for one dataset."""

    dataset_id: str
    required_fields: tuple[str, ...]
    lookback: Lookback
    pit_requirement: PitRequirement

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous dataset capability contracts."""
        fields = copy_sequence(self.required_fields, "required input fields")
        object.__setattr__(self, "required_fields", fields)
        require_text(self.dataset_id, "dataset ID")
        if not self.required_fields or len(set(self.required_fields)) != len(
            self.required_fields
        ):
            raise ValueError("required input fields must be non-empty and unique")
        for field_id in self.required_fields:
            require_text(field_id, "required input field")
        require_instance(self.lookback, Lookback, "invalid dataset lookback")
        require_enum_member(
            self.pit_requirement,
            PitRequirement,
            "invalid dataset PIT requirement",
        )

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a canonical JSON-ready requirement."""
        return {
            "dataset_id": self.dataset_id,
            "required_fields": sorted(self.required_fields),
            "lookback": {
                "value": self.lookback.value,
                "unit": self.lookback.unit.value,
            },
            "pit_requirement": self.pit_requirement.value,
        }


@dataclass(frozen=True, slots=True)
class LaneDatasetRequirement:
    """Per-dataset certified inputs for one asset lane."""

    lane: AssetLane
    requirements: tuple[DatasetInputRequirement, ...]

    def __post_init__(self) -> None:
        """Reject untyped lanes and duplicate dataset requirements."""
        requirements = copy_sequence(self.requirements, "lane dataset requirements")
        object.__setattr__(self, "requirements", requirements)
        require_enum_member(self.lane, AssetLane, "invalid asset lane")
        dataset_ids = tuple(item.dataset_id for item in self.requirements)
        if not dataset_ids or len(set(dataset_ids)) != len(dataset_ids):
            raise ValueError("lane dataset requirements must be non-empty and unique")

    @property
    def dataset_ids(self) -> tuple[str, ...]:
        """Return dataset IDs in declared order."""
        return tuple(item.dataset_id for item in self.requirements)

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a canonical lane requirement payload."""
        return {
            "lane": self.lane.value,
            "requirements": [
                item.resolved_payload
                for item in sorted(self.requirements, key=lambda item: item.dataset_id)
            ],
        }


def _lane_requirements_for(
    requirements: tuple[LaneDatasetRequirement, ...],
    lane: AssetLane,
) -> tuple[DatasetInputRequirement, ...]:
    require_enum_member(lane, AssetLane, "invalid asset lane")
    for requirement in requirements:
        if requirement.lane is lane:
            return requirement.requirements
    return ()


def _canonical_lane_requirements(
    requirements: tuple[LaneDatasetRequirement, ...],
) -> list[dict[str, object]]:
    return [
        item.resolved_payload
        for item in sorted(requirements, key=lambda item: item.lane.value)
    ]


@dataclass(frozen=True, slots=True)
class MaterializedIntermediate:
    """Content-bound time-series input consumed by a production expression."""

    column_id: str
    expression: str
    dependencies: tuple[str, ...]
    lookback: Lookback

    def __post_init__(self) -> None:
        """Reject incomplete intermediate computation contracts."""
        dependencies = copy_sequence(self.dependencies, "materialized dependencies")
        object.__setattr__(self, "dependencies", dependencies)
        require_text(self.column_id, "materialized intermediate column")
        require_text(self.expression, "materialized intermediate expression")
        if not self.dependencies or len(set(self.dependencies)) != len(
            self.dependencies
        ):
            raise ValueError("materialized intermediate dependencies must be unique")
        for dependency in self.dependencies:
            require_text(dependency, "materialized intermediate dependency")
        require_instance(
            self.lookback,
            Lookback,
            "invalid materialized intermediate lookback",
        )

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a canonical JSON-ready intermediate."""
        return {
            "column_id": self.column_id,
            "expression": self.expression,
            "dependencies": sorted(self.dependencies),
            "lookback": {
                "value": self.lookback.value,
                "unit": self.lookback.unit.value,
            },
        }


@dataclass(frozen=True, slots=True)
class PreprocessingContract:
    """Resolved preprocessing configuration included in the catalog hash."""

    steps: tuple[PreprocessingStep, ...]
    missing_value_policy: MissingValuePolicy
    winsorization: WinsorizationMethod
    standardization: StandardizationMethod
    applicable_lanes: frozenset[AssetLane]
    industry_neutralization_lanes: frozenset[AssetLane]
    size_neutralization_lanes: frozenset[AssetLane]
    industry_input_requirements: tuple[LaneDatasetRequirement, ...] = ()
    size_input_requirements: tuple[LaneDatasetRequirement, ...] = ()

    def __post_init__(self) -> None:
        """Copy lane sets and reject inconsistent preprocessing inputs."""
        object.__setattr__(
            self,
            "steps",
            copy_sequence(self.steps, "preprocessing steps"),
        )
        object.__setattr__(
            self,
            "industry_input_requirements",
            copy_sequence(
                self.industry_input_requirements,
                "industry preprocessing requirements",
            ),
        )
        object.__setattr__(
            self,
            "size_input_requirements",
            copy_sequence(
                self.size_input_requirements,
                "size preprocessing requirements",
            ),
        )
        object.__setattr__(self, "applicable_lanes", frozenset(self.applicable_lanes))
        object.__setattr__(
            self,
            "industry_neutralization_lanes",
            frozenset(self.industry_neutralization_lanes),
        )
        object.__setattr__(
            self,
            "size_neutralization_lanes",
            frozenset(self.size_neutralization_lanes),
        )
        for step in self.steps:
            require_enum_member(step, PreprocessingStep, "invalid preprocessing step")
        if len(self.steps) != len(set(self.steps)):
            raise ValueError("preprocessing steps must be unique")
        if not self.applicable_lanes:
            raise ValueError("preprocessing must apply to at least one lane")
        for lane in self.applicable_lanes:
            require_enum_member(lane, AssetLane, "invalid preprocessing asset lane")
        if not self.industry_neutralization_lanes <= self.applicable_lanes:
            raise ValueError("industry neutralization has an unsupported lane")
        if not self.size_neutralization_lanes <= self.applicable_lanes:
            raise ValueError("size neutralization has an unsupported lane")
        require_enum_member(
            self.missing_value_policy,
            MissingValuePolicy,
            "invalid missing-value policy",
        )
        require_enum_member(
            self.winsorization,
            WinsorizationMethod,
            "invalid winsorization method",
        )
        require_enum_member(
            self.standardization,
            StandardizationMethod,
            "invalid standardization method",
        )
        self._validate_input_requirements(
            self.industry_input_requirements,
            self.industry_neutralization_lanes,
            "industry",
        )
        self._validate_input_requirements(
            self.size_input_requirements,
            self.size_neutralization_lanes,
            "size",
        )

    @staticmethod
    def _validate_input_requirements(
        requirements: tuple[LaneDatasetRequirement, ...],
        lanes: frozenset[AssetLane],
        label: str,
    ) -> None:
        requirement_lanes = tuple(item.lane for item in requirements)
        if len(requirement_lanes) != len(set(requirement_lanes)):
            raise ValueError(f"duplicate {label} preprocessing requirements")
        if frozenset(requirement_lanes) != lanes:
            raise ValueError(f"{label} preprocessing requirements do not match lanes")

    def industry_requirements_for(
        self, lane: AssetLane
    ) -> tuple[DatasetInputRequirement, ...]:
        """Return explicit industry-neutralization inputs for a lane."""
        return _lane_requirements_for(self.industry_input_requirements, lane)

    def size_requirements_for(
        self, lane: AssetLane
    ) -> tuple[DatasetInputRequirement, ...]:
        """Return explicit size-neutralization inputs for a lane."""
        return _lane_requirements_for(self.size_input_requirements, lane)

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return the complete canonical preprocessing contract."""
        return {
            "steps": [step.value for step in self.steps],
            "missing_value_policy": self.missing_value_policy.value,
            "winsorization": self.winsorization.value,
            "standardization": self.standardization.value,
            "applicable_lanes": sorted(lane.value for lane in self.applicable_lanes),
            "industry_neutralization_lanes": sorted(
                lane.value for lane in self.industry_neutralization_lanes
            ),
            "size_neutralization_lanes": sorted(
                lane.value for lane in self.size_neutralization_lanes
            ),
            "industry_input_requirements": _canonical_lane_requirements(
                self.industry_input_requirements
            ),
            "size_input_requirements": _canonical_lane_requirements(
                self.size_input_requirements
            ),
        }


@dataclass(frozen=True, slots=True)
class CoreFactorSpecContract:
    """Content identity of a FactorSpec and its recursive dependency closure."""

    expression: str
    dependencies: tuple[str, ...]
    computation_type: Literal["expression", "python"]
    compiled_lookback: int | None
    effective_lookback: int
    leaf_dependencies: tuple[str, ...]
    dependency_graph_hash: str

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous factor computation identities."""
        object.__setattr__(
            self,
            "dependencies",
            copy_sequence(self.dependencies, "factor spec dependencies"),
        )
        object.__setattr__(
            self,
            "leaf_dependencies",
            copy_sequence(self.leaf_dependencies, "factor leaf dependencies"),
        )
        _validate_factor_expression(self.expression, self.computation_type)
        _validate_factor_dependencies(self.dependencies)
        if self.compiled_lookback is not None:
            _require_non_negative_int(self.compiled_lookback)
        _require_non_negative_int(self.effective_lookback)
        _validate_factor_leaf_dependencies(self.leaf_dependencies)
        if not _is_sha256_hex(self.dependency_graph_hash):
            raise ValueError("invalid factor dependency graph hash")

    @classmethod
    def from_spec(
        cls,
        spec: FactorSpec,
        registry: Mapping[str, FactorSpec],
    ) -> CoreFactorSpecContract:
        """Bind a FactorSpec and its recursive registry dependency closure."""
        compiled_lookback = _compiled_lookback(spec)
        graph_payload, leaf_dependencies, effective_lookback = (
            _resolve_factor_dependency_graph(
                spec,
                registry,
            )
        )
        graph_hash = hashlib.sha256(
            orjson.dumps(graph_payload, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        return cls(
            expression=spec.expression,
            dependencies=tuple(spec.dependencies),
            computation_type=spec.computation_type,
            compiled_lookback=compiled_lookback,
            effective_lookback=effective_lookback,
            leaf_dependencies=leaf_dependencies,
            dependency_graph_hash=graph_hash,
        )

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return the complete stable computation identity."""
        return {
            "expression": self.expression,
            "dependencies": sorted(self.dependencies),
            "computation_type": self.computation_type,
            "compiled_lookback": self.compiled_lookback,
            "effective_lookback": self.effective_lookback,
            "leaf_dependencies": sorted(self.leaf_dependencies),
            "dependency_graph_hash": self.dependency_graph_hash,
        }


def _validate_factor_expression(
    expression: object,
    computation_type: object,
) -> None:
    if not isinstance(expression, str):
        raise ValueError("factor expression must be a string")
    try:
        expression.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("factor expression must be valid UTF-8") from exc
    if computation_type not in ("expression", "python"):
        raise ValueError("invalid factor computation type")
    if computation_type == "expression" and not expression.strip():
        raise ValueError("expression factor cannot be empty")
    if computation_type == "python" and expression:
        raise ValueError("Python factor cannot carry a DSL expression")


def _validate_factor_dependencies(dependencies: tuple[str, ...]) -> None:
    if len(set(dependencies)) != len(dependencies):
        raise ValueError("factor spec dependencies must be unique")
    for dependency in dependencies:
        require_text(dependency, "factor spec dependency")


def _validate_factor_leaf_dependencies(dependencies: tuple[str, ...]) -> None:
    if not dependencies or len(set(dependencies)) != len(dependencies):
        raise ValueError("factor leaf dependencies must be non-empty and unique")
    for dependency in dependencies:
        require_text(dependency, "factor leaf dependency")


def _compiled_lookback(spec: FactorSpec) -> int | None:
    if spec.computation_type == "python":
        return None
    parsed = ExpressionParser(tokenize(spec.expression), spec.expression).parse()
    return analyze_expression(parsed).lookback


def _resolve_factor_dependency_graph(
    root: FactorSpec,
    registry: Mapping[str, FactorSpec],
) -> tuple[list[dict[str, object]], tuple[str, ...], int]:
    graph: dict[str, dict[str, object]] = {}
    leaves: set[str] = set()
    visiting: set[str] = set()
    effective_lookback = 0

    def visit(spec: FactorSpec) -> None:
        nonlocal effective_lookback
        if spec.id in visiting:
            raise ValueError(f"factor dependency cycle: {spec.id}")
        if spec.id in graph:
            return
        visiting.add(spec.id)
        compiled_lookback = _compiled_lookback(spec)
        effective_lookback = max(effective_lookback, compiled_lookback or 0)
        graph[spec.id] = {
            "factor_id": spec.id,
            "expression": spec.expression,
            "dependencies": sorted(spec.dependencies),
            "computation_type": spec.computation_type,
            "compiled_lookback": compiled_lookback,
            "calendar_context": _calendar_context_payload(spec),
        }
        for dependency in spec.dependencies:
            upstream = registry.get(dependency)
            if upstream is None:
                leaves.add(dependency)
            else:
                visit(upstream)
        visiting.remove(spec.id)

    visit(root)
    return (
        [graph[factor_id] for factor_id in sorted(graph)],
        tuple(sorted(leaves)),
        effective_lookback,
    )


def _calendar_context_payload(spec: FactorSpec) -> dict[str, object] | None:
    context = spec.calendar_context
    if context is None:
        return None
    return {
        "is_special": context.is_special,
        "is_half_day": context.is_half_day,
        "exchange": context.exchange,
    }


@dataclass(frozen=True, slots=True)
class CoreFactorDescriptor:
    """Governed metadata for one R3 daily factor."""

    factor_id: str
    lanes: frozenset[AssetLane]
    dataset_requirements: tuple[LaneDatasetRequirement, ...]
    lookback: Lookback
    pit_requirement: PitRequirement
    factor_spec: CoreFactorSpecContract
    benchmark_required: bool = False
    benchmark_requirement: DatasetInputRequirement | None = None
    neutralize_size: bool = True
    materialized_intermediates: tuple[MaterializedIntermediate, ...] = ()
    production_expression: str | None = None

    def __post_init__(self) -> None:
        """Copy lane sets and reject ambiguous governed metadata."""
        object.__setattr__(
            self,
            "dataset_requirements",
            copy_sequence(self.dataset_requirements, "factor dataset requirements"),
        )
        object.__setattr__(
            self,
            "materialized_intermediates",
            copy_sequence(
                self.materialized_intermediates,
                "factor materialized intermediates",
            ),
        )
        require_text(self.factor_id, "core factor ID")
        object.__setattr__(self, "lanes", frozenset(self.lanes))
        if not self.lanes:
            raise ValueError("core factor must support at least one lane")
        for lane in self.lanes:
            require_enum_member(lane, AssetLane, "invalid core factor lane")
        requirement_lanes = tuple(item.lane for item in self.dataset_requirements)
        if len(requirement_lanes) != len(set(requirement_lanes)):
            raise ValueError("core factor has duplicate lane dataset requirements")
        if frozenset(requirement_lanes) != self.lanes:
            raise ValueError("every supported lane needs an exact dataset requirement")
        require_instance(self.lookback, Lookback, "invalid core factor lookback")
        require_enum_member(
            self.pit_requirement,
            PitRequirement,
            "invalid core factor PIT requirement",
        )
        require_instance(
            self.factor_spec,
            CoreFactorSpecContract,
            "invalid core factor spec contract",
        )
        if self.benchmark_required != (self.benchmark_requirement is not None):
            raise ValueError("benchmark requirement and flag must agree")
        if self.factor_id == "log_free_float_cap" and self.neutralize_size:
            raise ValueError("size factor cannot be size-neutralized")
        intermediate_ids = tuple(
            item.column_id for item in self.materialized_intermediates
        )
        if len(intermediate_ids) != len(set(intermediate_ids)):
            raise ValueError("materialized intermediate IDs must be unique")

    def input_requirements_for(
        self, lane: AssetLane
    ) -> tuple[DatasetInputRequirement, ...]:
        """Return complete non-benchmark input requirements for a lane."""
        require_enum_member(lane, AssetLane, "invalid asset lane")
        for requirement in self.dataset_requirements:
            if requirement.lane is lane:
                return requirement.requirements
        raise ValueError(
            f"factor {self.factor_id!r} does not support lane {lane.value!r}"
        )

    def required_datasets_for(self, lane: AssetLane) -> tuple[str, ...]:
        """Return all dataset IDs, including the benchmark dataset."""
        dataset_ids = tuple(
            item.dataset_id for item in self.input_requirements_for(lane)
        )
        if self.benchmark_requirement is not None:
            dataset_ids = (*dataset_ids, self.benchmark_requirement.dataset_id)
        return dataset_ids

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return the complete canonical factor descriptor."""
        return {
            "factor_id": self.factor_id,
            "lanes": sorted(lane.value for lane in self.lanes),
            "dataset_requirements": _canonical_lane_requirements(
                self.dataset_requirements
            ),
            "lookback": {
                "value": self.lookback.value,
                "unit": self.lookback.unit.value,
            },
            "pit_requirement": self.pit_requirement.value,
            "factor_spec": self.factor_spec.resolved_payload,
            "benchmark_required": self.benchmark_required,
            "benchmark_requirement": (
                None
                if self.benchmark_requirement is None
                else self.benchmark_requirement.resolved_payload
            ),
            "neutralize_size": self.neutralize_size,
            "materialized_intermediates": [
                item.resolved_payload for item in self.materialized_intermediates
            ],
            "production_expression": self.production_expression,
        }


@dataclass(frozen=True, slots=True)
class CoreFactorCatalog:
    """Immutable, content-addressed R3 daily core-factor catalog."""

    descriptors: tuple[CoreFactorDescriptor, ...]
    preprocessing: PreprocessingContract
    version: str = "r3-core-daily-v1"

    def __post_init__(self) -> None:
        """Reject empty, duplicate, and unversioned catalogs."""
        descriptors = copy_sequence(self.descriptors, "core factor descriptors")
        object.__setattr__(self, "descriptors", descriptors)
        factor_ids = tuple(item.factor_id for item in self.descriptors)
        if not factor_ids or len(factor_ids) != len(set(factor_ids)):
            raise ValueError("core factor IDs must be non-empty and unique")
        require_text(self.version, "core factor catalog version")

    @property
    def factor_ids(self) -> tuple[str, ...]:
        """Return factor IDs in governed catalog order."""
        return tuple(item.factor_id for item in self.descriptors)

    def by_id(self, factor_id: str) -> CoreFactorDescriptor:
        """Resolve a descriptor by exact stable identifier."""
        for descriptor in self.descriptors:
            if descriptor.factor_id == factor_id:
                return descriptor
        raise KeyError(factor_id)

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return the complete canonical catalog payload."""
        return {
            "version": self.version,
            "descriptors": [item.resolved_payload for item in self.descriptors],
            "preprocessing": self.preprocessing.resolved_payload,
        }

    def recompute_payload_hash(self) -> str:
        """Recompute the SHA-256 identity from canonical content."""
        encoded = orjson.dumps(self.resolved_payload, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(encoded).hexdigest()

    @property
    def payload_hash(self) -> str:
        """Return the canonical content hash."""
        return self.recompute_payload_hash()
