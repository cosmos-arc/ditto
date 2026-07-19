"""Certified input evidence and fail-closed availability assessment for R3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ditto_features.factors.core_daily_catalog import R3_CORE_FACTOR_CATALOG
from ditto_features.factors.core_daily_contracts import (
    AssetLane,
    AvailabilityReason,
    CertifiedHistoryCoverage,
    CoreFactorDescriptor,
    DatasetInputRequirement,
    Lookback,
    PitRequirement,
    require_enum_member,
    require_instance,
    require_text,
)
from ditto_features.factors.core_daily_validation import copy_sequence

__all__ = [
    "AvailabilityContext",
    "CertifiedBenchmarkEvidence",
    "CoreFactorInputAvailability",
    "assess_core_factor_input_availability",
]


@dataclass(frozen=True, slots=True)
class CertifiedBenchmarkEvidence:
    """Pre-registered, concrete benchmark input certification."""

    benchmark_id: str
    dataset_id: str
    certified_fields: frozenset[str]
    certified_history: CertifiedHistoryCoverage
    certified_pit: PitRequirement

    def __post_init__(self) -> None:
        """Copy and validate externally supplied benchmark evidence."""
        require_text(self.benchmark_id, "benchmark ID")
        require_text(self.dataset_id, "benchmark dataset ID")
        fields = frozenset(self.certified_fields)
        if not fields:
            raise ValueError("certified benchmark fields cannot be empty")
        for field_id in fields:
            require_text(field_id, "certified benchmark field")
        require_instance(
            self.certified_history,
            CertifiedHistoryCoverage,
            "invalid certified benchmark history",
        )
        require_enum_member(
            self.certified_pit,
            PitRequirement,
            "invalid certified benchmark PIT evidence",
        )
        object.__setattr__(self, "certified_fields", fields)


def _empty_certified_fields() -> dict[str, frozenset[str]]:
    return {}


def _empty_certified_benchmarks() -> dict[str, CertifiedBenchmarkEvidence]:
    return {}


def _empty_certified_pit() -> dict[str, PitRequirement]:
    return {}


@dataclass(frozen=True, slots=True)
class AvailabilityContext:
    """Certified input evidence; it does not attest executor availability."""

    lane: AssetLane
    certified_datasets: frozenset[str]
    certified_history: Mapping[str, CertifiedHistoryCoverage]
    certified_fields: Mapping[str, frozenset[str]] = field(
        default_factory=_empty_certified_fields
    )
    benchmark_id: str | None = None
    certified_benchmarks: Mapping[str, CertifiedBenchmarkEvidence] = field(
        default_factory=_empty_certified_benchmarks
    )
    certified_pit: Mapping[str, PitRequirement] = field(
        default_factory=_empty_certified_pit
    )

    def __post_init__(self) -> None:
        """Defensively copy and validate all certified input evidence."""
        require_enum_member(self.lane, AssetLane, "invalid availability asset lane")
        datasets = frozenset(self.certified_datasets)
        for dataset_id in datasets:
            require_text(dataset_id, "certified dataset ID")
        history = _copy_certified_history(self.certified_history)
        fields = _copy_certified_fields(self.certified_fields)
        pit = _copy_certified_pit(self.certified_pit)
        if not set(history) <= datasets or not set(fields) <= datasets:
            raise ValueError("history and fields must belong to certified datasets")
        if not set(pit) <= datasets:
            raise ValueError("PIT evidence must belong to certified datasets")
        if self.benchmark_id is not None:
            require_text(self.benchmark_id, "benchmark ID")
        benchmarks = _copy_certified_benchmarks(self.certified_benchmarks)
        object.__setattr__(self, "certified_datasets", datasets)
        object.__setattr__(self, "certified_history", MappingProxyType(history))
        object.__setattr__(self, "certified_fields", MappingProxyType(fields))
        object.__setattr__(self, "certified_pit", MappingProxyType(pit))
        object.__setattr__(
            self,
            "certified_benchmarks",
            MappingProxyType(benchmarks),
        )


def _copy_certified_history(
    source: Mapping[str, CertifiedHistoryCoverage],
) -> dict[str, CertifiedHistoryCoverage]:
    history = dict(source)
    for dataset_id, coverage in history.items():
        require_text(dataset_id, "certified history dataset ID")
        require_instance(
            coverage,
            CertifiedHistoryCoverage,
            "invalid certified history coverage",
        )
    return history


def _copy_certified_fields(
    source: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    fields = {
        dataset_id: frozenset(field_ids) for dataset_id, field_ids in source.items()
    }
    for dataset_id, field_ids in fields.items():
        require_text(dataset_id, "certified fields dataset ID")
        for field_id in field_ids:
            require_text(field_id, "certified input field")
    return fields


def _copy_certified_pit(
    source: Mapping[str, PitRequirement],
) -> dict[str, PitRequirement]:
    pit = dict(source)
    for dataset_id, evidence in pit.items():
        require_text(dataset_id, "certified PIT dataset ID")
        require_enum_member(
            evidence,
            PitRequirement,
            "invalid certified dataset PIT evidence",
        )
    return pit


def _copy_certified_benchmarks(
    source: Mapping[str, CertifiedBenchmarkEvidence],
) -> dict[str, CertifiedBenchmarkEvidence]:
    benchmarks = dict(source)
    for benchmark_id, evidence in benchmarks.items():
        require_text(benchmark_id, "certified benchmark ID")
        require_instance(
            evidence,
            CertifiedBenchmarkEvidence,
            "invalid certified benchmark evidence",
        )
        if benchmark_id != evidence.benchmark_id:
            raise ValueError("certified benchmark key does not match evidence")
    return benchmarks


@dataclass(frozen=True, slots=True)
class CoreFactorInputAvailability:
    """Stable certified-input readiness decision for a governed factor."""

    certified_inputs_available: bool
    reason: AvailabilityReason | None = None
    dataset_ids: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Defensively copy sequence evidence at the public DTO boundary."""
        object.__setattr__(
            self,
            "dataset_ids",
            copy_sequence(self.dataset_ids, "availability dataset IDs"),
        )
        object.__setattr__(
            self,
            "missing_fields",
            copy_sequence(self.missing_fields, "availability missing fields"),
        )


def assess_core_factor_input_availability(
    descriptor: CoreFactorDescriptor,
    context: AvailabilityContext,
) -> CoreFactorInputAvailability:
    """Assess certified inputs only, without claiming an executor exists."""
    if context.lane not in descriptor.lanes:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.LANE_UNSUPPORTED,
        )

    input_failure = _assess_dataset_requirements(
        descriptor.input_requirements_for(context.lane),
        context,
    )
    if input_failure is not None:
        return input_failure

    benchmark_failure = _assess_benchmark_requirement(descriptor, context)
    if benchmark_failure is not None:
        return benchmark_failure

    preprocessing_requirements = (
        R3_CORE_FACTOR_CATALOG.preprocessing.industry_requirements_for(context.lane)
    )
    if descriptor.neutralize_size:
        preprocessing_requirements += (
            R3_CORE_FACTOR_CATALOG.preprocessing.size_requirements_for(context.lane)
        )
    preprocessing_failure = _assess_dataset_requirements(
        preprocessing_requirements,
        context,
    )
    if preprocessing_failure is not None:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.PREPROCESSING_INPUT_MISSING,
            preprocessing_failure.dataset_ids,
            preprocessing_failure.missing_fields,
        )
    return CoreFactorInputAvailability(True)


def _history_satisfies(
    coverage: CertifiedHistoryCoverage | None,
    lookback: Lookback,
) -> bool:
    return coverage is not None and coverage.amount_for(lookback.unit) >= lookback.value


_PIT_STRENGTH = {
    PitRequirement.NONE: 0,
    PitRequirement.KNOWN_AT: 1,
    PitRequirement.ANNOUNCEMENT_KNOWN_AT: 2,
}


def _pit_satisfies(
    evidence: PitRequirement,
    requirement: PitRequirement,
) -> bool:
    return _PIT_STRENGTH[evidence] >= _PIT_STRENGTH[requirement]


def _assess_dataset_requirements(
    requirements: tuple[DatasetInputRequirement, ...],
    context: AvailabilityContext,
) -> CoreFactorInputAvailability | None:
    uncertified = tuple(
        item.dataset_id
        for item in requirements
        if item.dataset_id not in context.certified_datasets
    )
    if uncertified:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.UNCERTIFIED_DATASET,
            _deduplicate(uncertified),
        )
    insufficient = tuple(
        item.dataset_id
        for item in requirements
        if not _history_satisfies(
            context.certified_history.get(item.dataset_id), item.lookback
        )
    )
    if insufficient:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.INSUFFICIENT_HISTORY,
            _deduplicate(insufficient),
        )
    missing_fields = tuple(
        field_id
        for item in requirements
        for field_id in item.required_fields
        if field_id not in context.certified_fields.get(item.dataset_id, frozenset())
    )
    if missing_fields:
        affected_datasets = tuple(
            item.dataset_id
            for item in requirements
            if any(
                field_id
                not in context.certified_fields.get(item.dataset_id, frozenset())
                for field_id in item.required_fields
            )
        )
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.UNCERTIFIED_INPUT_FIELD,
            _deduplicate(affected_datasets),
            _deduplicate(missing_fields),
        )
    missing_pit = tuple(
        item.dataset_id
        for item in requirements
        if not _pit_satisfies(
            context.certified_pit.get(item.dataset_id, PitRequirement.NONE),
            item.pit_requirement,
        )
    )
    if missing_pit:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.PIT_ALIGNMENT_MISSING,
            _deduplicate(missing_pit),
        )
    return None


def _assess_benchmark_requirement(
    descriptor: CoreFactorDescriptor,
    context: AvailabilityContext,
) -> CoreFactorInputAvailability | None:
    requirement = descriptor.benchmark_requirement
    if requirement is None:
        return None
    if context.benchmark_id is None:
        return CoreFactorInputAvailability(False, AvailabilityReason.BENCHMARK_MISSING)
    evidence = context.certified_benchmarks.get(context.benchmark_id)
    if evidence is None or evidence.dataset_id != requirement.dataset_id:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.BENCHMARK_UNCERTIFIED,
            (requirement.dataset_id,),
        )
    if not _history_satisfies(evidence.certified_history, requirement.lookback):
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.INSUFFICIENT_HISTORY,
            (requirement.dataset_id,),
        )
    missing_fields = tuple(
        field_id
        for field_id in requirement.required_fields
        if field_id not in evidence.certified_fields
    )
    if missing_fields:
        return CoreFactorInputAvailability(
            False,
            AvailabilityReason.UNCERTIFIED_INPUT_FIELD,
            (requirement.dataset_id,),
            missing_fields,
        )
    failure = None
    if not _pit_satisfies(evidence.certified_pit, requirement.pit_requirement):
        failure = CoreFactorInputAvailability(
            False,
            AvailabilityReason.PIT_ALIGNMENT_MISSING,
            (requirement.dataset_id,),
        )
    return failure


def _deduplicate(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
