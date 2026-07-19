"""Frozen R3 daily core-factor and preprocessing contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

import orjson

__all__ = [
    "R3_CORE_FACTOR_CATALOG",
    "AssetLane",
    "AvailabilityContext",
    "AvailabilityReason",
    "CertifiedHistoryCoverage",
    "CoreFactorCatalog",
    "CoreFactorDescriptor",
    "CoreFactorInputAvailability",
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
    "assess_core_factor_input_availability",
]


class AssetLane(StrEnum):
    """Supported R3 research lanes."""

    STOCK = "stock"
    ETF = "etf"


class LookbackUnit(StrEnum):
    """Unit attached to a factor lookback."""

    TRADING_DAYS = "trading_days"
    REPORTING_PERIODS = "reporting_periods"


class PitRequirement(StrEnum):
    """Point-in-time alignment strength required before a factor may run."""

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
    """Supported missing-value behavior for the R3 core catalog."""

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
    PIT_ALIGNMENT_MISSING = "pit_alignment_missing"


@dataclass(frozen=True, slots=True)
class Lookback:
    """An explicit lookback with a non-ambiguous unit."""

    value: int
    unit: LookbackUnit

    def __post_init__(self) -> None:
        """Reject zero or negative lookbacks."""
        if self.value < 1:
            raise ValueError("factor lookback must be positive")


@dataclass(frozen=True, slots=True)
class CertifiedHistoryCoverage:
    """Certified history extents measured in every supported lookback unit."""

    trading_days: int = 0
    reporting_periods: int = 0

    def __post_init__(self) -> None:
        """Reject negative or non-integral coverage evidence."""
        for value in (self.trading_days, self.reporting_periods):
            _require_non_negative_int(value)

    def amount_for(self, unit: LookbackUnit) -> int:
        """Return the certified extent in the requested unit."""
        if unit is LookbackUnit.TRADING_DAYS:
            return self.trading_days
        if unit is LookbackUnit.REPORTING_PERIODS:
            return self.reporting_periods
        raise ValueError(f"unsupported lookback unit: {unit!r}")


@dataclass(frozen=True, slots=True)
class LaneDatasetRequirement:
    """Certified datasets required by one asset lane."""

    lane: AssetLane
    dataset_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject empty or duplicate dataset identifiers."""
        if not self.dataset_ids or len(set(self.dataset_ids)) != len(self.dataset_ids):
            raise ValueError("lane dataset requirements must be non-empty and unique")
        if any(not dataset_id.strip() for dataset_id in self.dataset_ids):
            raise ValueError("dataset IDs cannot be empty")


@dataclass(frozen=True, slots=True)
class MaterializedIntermediate:
    """Content-bound time-series input consumed by a production expression."""

    column_id: str
    expression: str
    dependencies: tuple[str, ...]
    lookback: Lookback

    def __post_init__(self) -> None:
        """Reject incomplete intermediate computation contracts."""
        if not self.column_id.strip() or not self.expression.strip():
            raise ValueError("materialized intermediate identity cannot be empty")
        if not self.dependencies or len(set(self.dependencies)) != len(
            self.dependencies
        ):
            raise ValueError("materialized intermediate dependencies must be unique")

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a JSON-ready deterministic representation."""
        return {
            "column_id": self.column_id,
            "expression": self.expression,
            "dependencies": list(self.dependencies),
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

    def __post_init__(self) -> None:
        """Reject incomplete or internally inconsistent preprocessing."""
        for step in self.steps:
            _require_enum_member(
                step,
                PreprocessingStep,
                "invalid preprocessing step",
            )
        if len(self.steps) != len(set(self.steps)):
            raise ValueError("preprocessing steps must be unique")
        if not self.applicable_lanes:
            raise ValueError("preprocessing must apply to at least one lane")
        if not self.industry_neutralization_lanes <= self.applicable_lanes:
            raise ValueError("industry neutralization has an unsupported lane")
        if not self.size_neutralization_lanes <= self.applicable_lanes:
            raise ValueError("size neutralization has an unsupported lane")
        _require_enum_member(
            self.missing_value_policy,
            MissingValuePolicy,
            "invalid missing-value policy",
        )
        _require_enum_member(
            self.winsorization,
            WinsorizationMethod,
            "invalid winsorization method",
        )
        _require_enum_member(
            self.standardization,
            StandardizationMethod,
            "invalid standardization method",
        )

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a JSON-ready deterministic representation."""
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
        }


def _require_enum_member(
    value: object,
    enum_type: type[StrEnum],
    error_message: str,
) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(error_message)


def _require_non_negative_int(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("certified history coverage must be non-negative ints")


@dataclass(frozen=True, slots=True)
class CoreFactorDescriptor:
    """Governed metadata for one member of the R3 daily core catalog."""

    factor_id: str
    lanes: frozenset[AssetLane]
    dataset_requirements: tuple[LaneDatasetRequirement, ...]
    lookback: Lookback
    pit_requirement: PitRequirement
    benchmark_required: bool = False
    neutralize_size: bool = True
    materialized_intermediates: tuple[MaterializedIntermediate, ...] = ()
    production_expression: str | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous factor metadata at construction time."""
        if not self.factor_id.strip():
            raise ValueError("core factor ID cannot be empty")
        if not self.lanes:
            raise ValueError("core factor must support at least one lane")
        requirement_lanes = tuple(item.lane for item in self.dataset_requirements)
        if len(requirement_lanes) != len(set(requirement_lanes)):
            raise ValueError("core factor has duplicate lane dataset requirements")
        if frozenset(requirement_lanes) != self.lanes:
            raise ValueError("every supported lane needs an exact dataset requirement")
        if self.factor_id == "log_free_float_cap" and self.neutralize_size:
            raise ValueError("size factor cannot be size-neutralized")
        intermediate_ids = tuple(
            item.column_id for item in self.materialized_intermediates
        )
        if len(intermediate_ids) != len(set(intermediate_ids)):
            raise ValueError("materialized intermediate IDs must be unique")

    def required_datasets_for(self, lane: AssetLane) -> tuple[str, ...]:
        """Return the exact dataset IDs for ``lane`` or fail closed."""
        for requirement in self.dataset_requirements:
            if requirement.lane is lane:
                return requirement.dataset_ids
        raise ValueError(
            f"factor {self.factor_id!r} does not support lane {lane.value!r}"
        )

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return a JSON-ready deterministic representation."""
        return {
            "factor_id": self.factor_id,
            "lanes": sorted(lane.value for lane in self.lanes),
            "dataset_requirements": [
                {"lane": item.lane.value, "dataset_ids": list(item.dataset_ids)}
                for item in self.dataset_requirements
            ],
            "lookback": {
                "value": self.lookback.value,
                "unit": self.lookback.unit.value,
            },
            "pit_requirement": self.pit_requirement.value,
            "benchmark_required": self.benchmark_required,
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
        """Reject empty, duplicate, or unversioned catalogs."""
        factor_ids = tuple(item.factor_id for item in self.descriptors)
        if not factor_ids or len(factor_ids) != len(set(factor_ids)):
            raise ValueError("core factor IDs must be non-empty and unique")
        if not self.version.strip():
            raise ValueError("core factor catalog version cannot be empty")

    @property
    def factor_ids(self) -> tuple[str, ...]:
        """Return factor identifiers in governed catalog order."""
        return tuple(item.factor_id for item in self.descriptors)

    def by_id(self, factor_id: str) -> CoreFactorDescriptor:
        """Resolve a governed descriptor by exact stable identifier."""
        for descriptor in self.descriptors:
            if descriptor.factor_id == factor_id:
                return descriptor
        raise KeyError(factor_id)

    @property
    def resolved_payload(self) -> dict[str, object]:
        """Return the complete JSON-ready governed payload."""
        return {
            "version": self.version,
            "descriptors": [item.resolved_payload for item in self.descriptors],
            "preprocessing": self.preprocessing.resolved_payload,
        }

    def recompute_payload_hash(self) -> str:
        """Recompute the canonical content hash from current state."""
        encoded = orjson.dumps(
            self.resolved_payload,
            option=orjson.OPT_SORT_KEYS,
        )
        return hashlib.sha256(encoded).hexdigest()

    @property
    def payload_hash(self) -> str:
        """Return the canonical content hash."""
        return self.recompute_payload_hash()


@dataclass(frozen=True, slots=True)
class AvailabilityContext:
    """Certified input evidence; it does not attest executor availability."""

    lane: AssetLane
    certified_datasets: frozenset[str]
    certified_history: Mapping[str, CertifiedHistoryCoverage]
    benchmark_id: str | None = None
    pit_aligned_datasets: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Reject invalid certified-history evidence."""
        history = dict(self.certified_history)
        for dataset_id, coverage in history.items():
            if not dataset_id.strip():
                raise ValueError("certified history dataset ID cannot be empty")
            _require_history_coverage(coverage)
        object.__setattr__(self, "certified_history", MappingProxyType(history))


@dataclass(frozen=True, slots=True)
class CoreFactorInputAvailability:
    """Stable certified-input readiness decision for a governed core factor."""

    certified_inputs_available: bool
    reason: AvailabilityReason | None = None
    dataset_ids: tuple[str, ...] = ()


def assess_core_factor_input_availability(
    descriptor: CoreFactorDescriptor,
    context: AvailabilityContext,
) -> CoreFactorInputAvailability:
    """Assess certified inputs only, without claiming a Python executor exists."""
    if context.lane not in descriptor.lanes:
        return CoreFactorInputAvailability(
            certified_inputs_available=False,
            reason=AvailabilityReason.LANE_UNSUPPORTED,
        )

    required = descriptor.required_datasets_for(context.lane)
    uncertified = tuple(
        dataset_id
        for dataset_id in required
        if dataset_id not in context.certified_datasets
    )
    if uncertified:
        return CoreFactorInputAvailability(
            certified_inputs_available=False,
            reason=AvailabilityReason.UNCERTIFIED_DATASET,
            dataset_ids=uncertified,
        )

    insufficient = tuple(
        dataset_id
        for dataset_id in required
        if not _history_satisfies(
            context.certified_history.get(dataset_id),
            descriptor.lookback,
        )
    )
    if insufficient:
        return CoreFactorInputAvailability(
            certified_inputs_available=False,
            reason=AvailabilityReason.INSUFFICIENT_HISTORY,
            dataset_ids=insufficient,
        )

    if descriptor.benchmark_required and not (
        context.benchmark_id and context.benchmark_id.strip()
    ):
        return CoreFactorInputAvailability(
            certified_inputs_available=False,
            reason=AvailabilityReason.BENCHMARK_MISSING,
        )

    if descriptor.pit_requirement is not PitRequirement.NONE:
        missing_pit = tuple(
            dataset_id
            for dataset_id in required
            if dataset_id not in context.pit_aligned_datasets
        )
        if missing_pit:
            return CoreFactorInputAvailability(
                certified_inputs_available=False,
                reason=AvailabilityReason.PIT_ALIGNMENT_MISSING,
                dataset_ids=missing_pit,
            )

    return CoreFactorInputAvailability(certified_inputs_available=True)


def _require_history_coverage(value: object) -> None:
    if not isinstance(value, CertifiedHistoryCoverage):
        raise ValueError("invalid certified history coverage")


def _history_satisfies(
    coverage: CertifiedHistoryCoverage | None,
    lookback: Lookback,
) -> bool:
    return coverage is not None and coverage.amount_for(lookback.unit) >= lookback.value


_MARKET_LANES = frozenset({AssetLane.STOCK, AssetLane.ETF})
_STOCK_LANE = frozenset({AssetLane.STOCK})
_MARKET_REQUIREMENTS = (
    LaneDatasetRequirement(AssetLane.STOCK, ("stock_daily",)),
    LaneDatasetRequirement(AssetLane.ETF, ("etf_daily",)),
)
_BENCHMARK_REQUIREMENTS = (
    LaneDatasetRequirement(AssetLane.STOCK, ("stock_daily", "index_daily")),
    LaneDatasetRequirement(AssetLane.ETF, ("etf_daily", "index_daily")),
)

_PREPROCESSING = PreprocessingContract(
    steps=(
        PreprocessingStep.PIT_ALIGNMENT,
        PreprocessingStep.COVERAGE_VALIDATION,
        PreprocessingStep.MISSING_VALUE_POLICY,
        PreprocessingStep.WINSORIZATION,
        PreprocessingStep.NEUTRALIZATION,
        PreprocessingStep.STANDARDIZATION,
        PreprocessingStep.WEIGHTED_SCORING,
    ),
    missing_value_policy=MissingValuePolicy.DROP,
    winsorization=WinsorizationMethod.MAD_3,
    standardization=StandardizationMethod.ZSCORE,
    applicable_lanes=_MARKET_LANES,
    industry_neutralization_lanes=_STOCK_LANE,
    size_neutralization_lanes=_STOCK_LANE,
)


def _market_descriptor(
    factor_id: str,
    lookback: int,
    *,
    benchmark_required: bool = False,
    materialized_intermediates: tuple[MaterializedIntermediate, ...] = (),
    production_expression: str | None = None,
) -> CoreFactorDescriptor:
    return CoreFactorDescriptor(
        factor_id=factor_id,
        lanes=_MARKET_LANES,
        dataset_requirements=(
            _BENCHMARK_REQUIREMENTS if benchmark_required else _MARKET_REQUIREMENTS
        ),
        lookback=Lookback(lookback, LookbackUnit.TRADING_DAYS),
        pit_requirement=PitRequirement.KNOWN_AT,
        benchmark_required=benchmark_required,
        materialized_intermediates=materialized_intermediates,
        production_expression=production_expression,
    )


def _stock_descriptor(
    factor_id: str,
    datasets: tuple[str, ...],
    lookback: Lookback,
    *,
    pit_requirement: PitRequirement = PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    neutralize_size: bool = True,
) -> CoreFactorDescriptor:
    return CoreFactorDescriptor(
        factor_id=factor_id,
        lanes=_STOCK_LANE,
        dataset_requirements=(LaneDatasetRequirement(AssetLane.STOCK, datasets),),
        lookback=lookback,
        pit_requirement=pit_requirement,
        neutralize_size=neutralize_size,
    )


R3_CORE_FACTOR_CATALOG = CoreFactorCatalog(
    descriptors=(
        _market_descriptor("momentum_1m", 20),
        _market_descriptor("momentum_3m", 60),
        _market_descriptor("reversal_1w", 5),
        _market_descriptor("volatility_factor", 20),
        _market_descriptor("vol_ratio", 60),
        _market_descriptor(
            "liquidity",
            20,
            materialized_intermediates=(
                MaterializedIntermediate(
                    column_id="ts_mean_daily_amount_20d",
                    expression="ts_mean(market.volume * market.close, 20)",
                    dependencies=("market.volume", "market.close"),
                    lookback=Lookback(20, LookbackUnit.TRADING_DAYS),
                ),
            ),
            production_expression="cs_rank(ts_mean_daily_amount_20d)",
        ),
        _market_descriptor("relative_strength_60d", 60, benchmark_required=True),
        _stock_descriptor(
            "ep_ttm",
            ("stock_daily", "income_statement"),
            Lookback(4, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "bp_ratio",
            ("stock_daily", "balance_sheet"),
            Lookback(1, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "quality_roe",
            ("balance_sheet", "income_statement"),
            Lookback(1, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "revenue_growth",
            ("income_statement",),
            Lookback(4, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "log_free_float_cap",
            ("stock_daily", "valuation_metrics"),
            Lookback(1, LookbackUnit.TRADING_DAYS),
            pit_requirement=PitRequirement.KNOWN_AT,
            neutralize_size=False,
        ),
    ),
    preprocessing=_PREPROCESSING,
)
