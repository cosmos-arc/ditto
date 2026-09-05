"""Immutable stock/ETF selection inputs and saved-run contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ditto_kernel.identity import InstrumentId

from ditto_strategy.selection._validation import (
    error as _error,
)
from ditto_strategy.selection._validation import (
    finite as _finite,
)
from ditto_strategy.selection._validation import (
    optional_bool as _optional_bool,
)
from ditto_strategy.selection._validation import (
    optional_finite as _optional_finite,
)
from ditto_strategy.selection._validation import (
    optional_non_negative_int as _optional_non_negative_int,
)
from ditto_strategy.selection._validation import (
    optional_text as _optional_text,
)
from ditto_strategy.selection._validation import (
    ordered_sequence as _ordered_sequence,
)
from ditto_strategy.selection._validation import (
    positive_int as _positive_int,
)
from ditto_strategy.selection._validation import (
    text as _text,
)
from ditto_strategy.selection._validation import (
    text_set as _text_set,
)
from ditto_strategy.selection._validation import (
    unit as _unit,
)
from ditto_strategy.selection._validation import (
    validate_temporal_visibility as _validate_temporal_visibility,
)
from ditto_strategy.selection.canonical import (
    canonical_input_hash as _canonical_input_hash_impl,
)
from ditto_strategy.selection.canonical import (
    canonical_run_hash as _canonical_run_hash_impl,
)
from ditto_strategy.selection.canonical import (
    canonical_run_payload as _canonical_run_payload_impl,
)
from ditto_strategy.selection.canonical import (
    canonical_spec_hash as _canonical_spec_hash_impl,
)

__all__ = [
    "EtfSelectionSpec",
    "SelectionAssetKind",
    "SelectionCandidate",
    "SelectionExclusion",
    "SelectionExclusionReason",
    "SelectionFactorContribution",
    "SelectionFactorValue",
    "SelectionFactorWeight",
    "SelectionInputBundle",
    "SelectionInstrumentInput",
    "SelectionLimitState",
    "SelectionRun",
    "SelectionRunStatus",
    "SelectionSpec",
    "StockSelectionSpec",
    "canonical_input_hash",
    "canonical_run_hash",
    "canonical_run_payload",
    "canonical_spec_hash",
]

_SHA256_HEX_LENGTH = 64


class SelectionAssetKind(StrEnum):
    """Two deliberately distinct selection lanes."""

    STOCK = "stock"
    ETF = "etf"


class SelectionLimitState(StrEnum):
    """Tradability at the decision cutoff."""

    NORMAL = "normal"
    LIMIT_UP = "limit_up"
    LIMIT_DOWN = "limit_down"


class SelectionExclusionReason(StrEnum):
    """Stable first-failure reason codes for why an instrument is out."""

    MISSING_DATA = "missing_data"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    ST_STATUS = "st_status"
    SUSPENDED = "suspended"
    INSUFFICIENT_LISTING_DAYS = "insufficient_listing_days"
    PRICE_LIMITED = "price_limited"
    EXCESSIVE_TRACKING_ERROR = "excessive_tracking_error"
    BELOW_TOP_K = "below_top_k"


class SelectionRunStatus(StrEnum):
    """Completeness of a selection run."""

    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SelectionFactorWeight:
    """One additive factor declaration in a SelectionSpec."""

    name: str
    weight: float

    def __post_init__(self) -> None:
        """Validate a normalized, non-negative factor weight."""
        object.__setattr__(self, "name", _text(self.name, field_name="factor name"))
        weight = _finite(self.weight, field_name="factor weight", minimum=0.0)
        if weight > 1.0:
            raise _error(
                "selection factor weight must be at most one",
                reason="invalid_selection_factor_weight",
            )
        object.__setattr__(self, "weight", weight)


def _validated_weights(value: object) -> tuple[SelectionFactorWeight, ...]:
    weights = _ordered_sequence(
        value,
        item_type=SelectionFactorWeight,
        field_name="factor_weights",
    )
    names = tuple(item.name for item in weights)
    if not weights or len(set(names)) != len(names):
        raise _error(
            "selection requires unique factor weights",
            reason="invalid_selection_factor_weights",
        )
    if not math.isclose(sum(item.weight for item in weights), 1.0, abs_tol=1e-12):
        raise _error(
            "selection factor weights must sum to one",
            reason="invalid_selection_factor_weight_total",
        )
    return tuple(sorted(weights, key=lambda item: item.name))


def _validated_limit_states(value: object) -> tuple[SelectionLimitState, ...]:
    states = _ordered_sequence(
        value,
        item_type=SelectionLimitState,
        field_name="excluded_limit_states",
    )
    if len(set(states)) != len(states) or SelectionLimitState.NORMAL in states:
        raise _error(
            "selection excluded_limit_states must be unique non-normal states",
            reason="invalid_selection_limit_policy",
        )
    return tuple(sorted(states, key=lambda item: item.value))


def _validate_spec(value: StockSelectionSpec | EtfSelectionSpec) -> None:
    for field_name in ("spec_id", "spec_version"):
        object.__setattr__(
            value,
            field_name,
            _text(getattr(value, field_name), field_name=field_name),
        )
    _positive_int(value.top_k, field_name="top_k")
    object.__setattr__(
        value,
        "min_average_turnover",
        _finite(
            value.min_average_turnover,
            field_name="min_average_turnover",
            minimum=0.0,
        ),
    )
    _positive_int(value.min_listing_days, field_name="min_listing_days")
    object.__setattr__(
        value, "factor_weights", _validated_weights(value.factor_weights)
    )
    object.__setattr__(
        value,
        "excluded_limit_states",
        _validated_limit_states(value.excluded_limit_states),
    )


@dataclass(frozen=True, slots=True)
class StockSelectionSpec:
    """Stock-only hard filters and additive scoring policy."""

    spec_id: str
    spec_version: str
    top_k: int
    min_average_turnover: float
    min_listing_days: int
    factor_weights: tuple[SelectionFactorWeight, ...]
    excluded_limit_states: tuple[SelectionLimitState, ...] = (
        SelectionLimitState.LIMIT_UP,
        SelectionLimitState.LIMIT_DOWN,
    )

    def __post_init__(self) -> None:
        """Validate stock-specific selection policy fields."""
        _validate_spec(self)

    @property
    def asset_kind(self) -> SelectionAssetKind:
        """Identify the stock selection lane."""
        return SelectionAssetKind.STOCK


@dataclass(frozen=True, slots=True)
class EtfSelectionSpec:
    """ETF-only liquidity, age, tracking, and additive scoring policy."""

    spec_id: str
    spec_version: str
    top_k: int
    min_average_turnover: float
    min_listing_days: int
    factor_weights: tuple[SelectionFactorWeight, ...]
    max_tracking_error: float | None = None
    excluded_limit_states: tuple[SelectionLimitState, ...] = (
        SelectionLimitState.LIMIT_UP,
        SelectionLimitState.LIMIT_DOWN,
    )

    def __post_init__(self) -> None:
        """Validate ETF-specific selection policy fields."""
        _validate_spec(self)
        object.__setattr__(
            self,
            "max_tracking_error",
            _optional_finite(
                self.max_tracking_error,
                field_name="max_tracking_error",
                minimum=0.0,
            ),
        )

    @property
    def asset_kind(self) -> SelectionAssetKind:
        """Identify the ETF selection lane."""
        return SelectionAssetKind.ETF


type SelectionSpec = StockSelectionSpec | EtfSelectionSpec


@dataclass(frozen=True, slots=True)
class SelectionFactorValue:
    """One normalized factor observation for an instrument."""

    name: str
    value: float

    def __post_init__(self) -> None:
        """Validate one normalized finite factor observation."""
        object.__setattr__(self, "name", _text(self.name, field_name="factor name"))
        object.__setattr__(
            self,
            "value",
            _unit(self.value, field_name="factor value"),
        )


@dataclass(frozen=True, slots=True)
class SelectionInstrumentInput:
    """Normalized feature and hard-filter facts for one instrument."""

    instrument_id: InstrumentId
    instrument_name: str
    industry_id: str | None
    factor_values: tuple[SelectionFactorValue, ...]
    average_turnover: float | None
    is_st: bool | None
    is_suspended: bool | None
    listing_days: int | None
    limit_state: SelectionLimitState | None
    tracking_error: float | None
    declared_missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Freeze factor facts and validate hard-filter observations."""
        _positive_int(self.instrument_id, field_name="instrument_id")
        object.__setattr__(
            self,
            "instrument_name",
            _text(self.instrument_name, field_name="instrument_name"),
        )
        object.__setattr__(
            self,
            "industry_id",
            _optional_text(self.industry_id, field_name="industry_id"),
        )
        factors = _ordered_sequence(
            self.factor_values,
            item_type=SelectionFactorValue,
            field_name="factor_values",
        )
        names = tuple(item.name for item in factors)
        if len(set(names)) != len(names):
            raise _error(
                "selection instrument requires unique factor values",
                reason="duplicate_selection_factor",
                instrument_id=self.instrument_id,
            )
        object.__setattr__(
            self,
            "factor_values",
            tuple(sorted(factors, key=lambda item: item.name)),
        )
        object.__setattr__(
            self,
            "average_turnover",
            _optional_finite(
                self.average_turnover,
                field_name="average_turnover",
                minimum=0.0,
            ),
        )
        for field_name in ("is_st", "is_suspended"):
            object.__setattr__(
                self,
                field_name,
                _optional_bool(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "listing_days",
            _optional_non_negative_int(self.listing_days, field_name="listing_days"),
        )
        limit_state: object = object.__getattribute__(self, "limit_state")
        if limit_state is not None and not isinstance(limit_state, SelectionLimitState):
            raise _error(
                "selection limit_state must be SelectionLimitState or None",
                reason="invalid_selection_limit_state",
            )
        object.__setattr__(
            self,
            "tracking_error",
            _optional_finite(
                self.tracking_error,
                field_name="tracking_error",
                minimum=0.0,
            ),
        )
        object.__setattr__(
            self,
            "declared_missing_inputs",
            _text_set(
                self.declared_missing_inputs, field_name="declared_missing_inputs"
            ),
        )


@dataclass(frozen=True, slots=True)
class SelectionInputBundle:
    """Exact PIT and source identity for one selection execution."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    spec: SelectionSpec
    seed: int
    instruments: tuple[SelectionInstrumentInput, ...]

    def __post_init__(self) -> None:
        """Freeze input order and reject future-visible evidence."""
        for field_name in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise _error(
                    f"selection {field_name} must be timezone-aware",
                    reason="invalid_selection_time",
                    field_name=field_name,
                )
        if self.publication_cutoff > self.knowledge_cutoff:
            raise _error(
                "selection publication_cutoff exceeds knowledge_cutoff",
                reason="invalid_selection_cutoff",
            )
        if self.knowledge_cutoff > self.as_of:
            raise _error(
                "selection knowledge_cutoff exceeds as_of",
                reason="invalid_selection_cutoff",
            )
        object.__setattr__(
            self,
            "universe_snapshot_id",
            _text(self.universe_snapshot_id, field_name="universe_snapshot_id"),
        )
        object.__setattr__(
            self,
            "industry_rotation_snapshot_id",
            _optional_text(
                self.industry_rotation_snapshot_id,
                field_name="industry_rotation_snapshot_id",
            ),
        )
        object.__setattr__(
            self,
            "source_snapshot_ids",
            _text_set(self.source_snapshot_ids, field_name="source_snapshot_ids"),
        )
        if not self.source_snapshot_ids:
            raise _error(
                "selection requires source_snapshot_ids",
                reason="missing_selection_lineage",
            )
        spec: object = object.__getattribute__(self, "spec")
        if not isinstance(spec, StockSelectionSpec | EtfSelectionSpec):
            raise _error(
                "selection spec must be StockSelectionSpec or EtfSelectionSpec",
                reason="invalid_selection_spec",
            )
        if type(self.seed) is not int or self.seed < 0:
            raise _error(
                "selection seed must be a non-negative integer",
                reason="invalid_selection_seed",
            )
        instruments = _ordered_sequence(
            self.instruments,
            item_type=SelectionInstrumentInput,
            field_name="instruments",
        )
        instrument_ids = tuple(item.instrument_id for item in instruments)
        if len(set(instrument_ids)) != len(instrument_ids):
            raise _error(
                "selection requires unique instrument_id values",
                reason="duplicate_selection_instrument",
            )
        object.__setattr__(
            self,
            "instruments",
            tuple(sorted(instruments, key=lambda item: item.instrument_id)),
        )

    @property
    def input_hash(self) -> str:
        """Return the canonical identity of all execution inputs."""
        return _canonical_input_hash(self)

    @property
    def spec_hash(self) -> str:
        """Return the canonical identity of the embedded SelectionSpec."""
        return _canonical_spec_hash(self.spec)


@dataclass(frozen=True, slots=True)
class SelectionFactorContribution:
    """One additive factor contribution to a selected score."""

    factor_name: str
    value: float
    weight: float
    contribution: float

    def __post_init__(self) -> None:
        """Validate one additive contribution."""
        object.__setattr__(
            self,
            "factor_name",
            _text(self.factor_name, field_name="factor_name"),
        )
        object.__setattr__(self, "value", _unit(self.value, field_name="value"))
        object.__setattr__(
            self,
            "weight",
            _finite(self.weight, field_name="weight", minimum=0.0),
        )
        object.__setattr__(
            self,
            "contribution",
            _unit(self.contribution, field_name="contribution"),
        )


@dataclass(frozen=True, slots=True)
class SelectionCandidate:
    """One selected instrument and its immutable ranking evidence."""

    instrument_id: InstrumentId
    instrument_name: str
    industry_id: str | None
    rank: int
    score: float
    factor_contributions: tuple[SelectionFactorContribution, ...]

    def __post_init__(self) -> None:
        """Validate contiguous ranking evidence and additive score."""
        _positive_int(self.instrument_id, field_name="instrument_id")
        object.__setattr__(
            self,
            "instrument_name",
            _text(self.instrument_name, field_name="instrument_name"),
        )
        object.__setattr__(
            self,
            "industry_id",
            _optional_text(self.industry_id, field_name="industry_id"),
        )
        _positive_int(self.rank, field_name="rank")
        object.__setattr__(self, "score", _unit(self.score, field_name="score"))
        contributions = _ordered_sequence(
            self.factor_contributions,
            item_type=SelectionFactorContribution,
            field_name="factor_contributions",
        )
        if not math.isclose(
            sum(item.contribution for item in contributions),
            self.score,
            abs_tol=1e-12,
        ):
            raise _error(
                "selection candidate score does not match factor contributions",
                reason="invalid_selection_score_total",
            )
        object.__setattr__(self, "factor_contributions", contributions)


@dataclass(frozen=True, slots=True)
class SelectionExclusion:
    """The stable first reason an input instrument was not selected."""

    instrument_id: InstrumentId
    instrument_name: str
    reason_code: SelectionExclusionReason
    stage: str
    detail: str

    def __post_init__(self) -> None:
        """Validate stable exclusion evidence."""
        _positive_int(self.instrument_id, field_name="instrument_id")
        reason_code: object = object.__getattribute__(self, "reason_code")
        if not isinstance(reason_code, SelectionExclusionReason):
            raise _error(
                "selection exclusion reason_code must be SelectionExclusionReason",
                reason="invalid_selection_exclusion_reason",
            )
        for field_name in ("instrument_name", "stage", "detail"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class SelectionRun:
    """Saved, replayable selection result shared by stock and ETF lanes."""

    input_hash: str
    spec_hash: str
    asset_kind: SelectionAssetKind
    spec_id: str
    spec_version: str
    seed: int
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    status: SelectionRunStatus
    candidates: tuple[SelectionCandidate, ...]
    exclusions: tuple[SelectionExclusion, ...]
    missing_inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate one complete and non-overlapping saved result."""
        for field_name in ("input_hash", "spec_hash"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str)
                or len(value) != _SHA256_HEX_LENGTH
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise _error(
                    f"selection {field_name} must be lowercase SHA-256",
                    reason="invalid_selection_hash",
                    field_name=field_name,
                )
        asset_kind: object = object.__getattribute__(self, "asset_kind")
        if not isinstance(asset_kind, SelectionAssetKind):
            raise _error(
                "selection asset_kind must be SelectionAssetKind",
                reason="invalid_selection_asset_kind",
            )
        status: object = object.__getattribute__(self, "status")
        if not isinstance(status, SelectionRunStatus):
            raise _error(
                "selection status must be SelectionRunStatus",
                reason="invalid_selection_run_status",
            )
        for field_name in ("spec_id", "spec_version", "universe_snapshot_id"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "industry_rotation_snapshot_id",
            _optional_text(
                self.industry_rotation_snapshot_id,
                field_name="industry_rotation_snapshot_id",
            ),
        )
        if type(self.seed) is not int or self.seed < 0:
            raise _error(
                "selection seed must be a non-negative integer",
                reason="invalid_selection_seed",
            )
        _validate_temporal_visibility(self)
        object.__setattr__(
            self,
            "source_snapshot_ids",
            _text_set(self.source_snapshot_ids, field_name="source_snapshot_ids"),
        )
        candidates = _ordered_sequence(
            self.candidates,
            item_type=SelectionCandidate,
            field_name="candidates",
        )
        if tuple(item.rank for item in candidates) != tuple(
            range(1, len(candidates) + 1)
        ):
            raise _error(
                "selection candidate ranks must be contiguous and ordered",
                reason="invalid_selection_rank_order",
            )
        exclusions = _ordered_sequence(
            self.exclusions,
            item_type=SelectionExclusion,
            field_name="exclusions",
        )
        all_ids = [item.instrument_id for item in (*candidates, *exclusions)]
        if len(set(all_ids)) != len(all_ids):
            raise _error(
                "selection outputs require unique instrument IDs",
                reason="duplicate_selection_output",
            )
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "exclusions", exclusions)
        object.__setattr__(
            self,
            "missing_inputs",
            _text_set(self.missing_inputs, field_name="missing_inputs"),
        )

    @property
    def run_id(self) -> str:
        """Return the content-addressed saved-run identity."""
        return f"selection-run:sha256:{_canonical_run_hash(self)}"


def _canonical_spec_hash(value: SelectionSpec) -> str:
    return _canonical_spec_hash_impl(value)


def _canonical_input_hash(value: SelectionInputBundle) -> str:
    return _canonical_input_hash_impl(value)


def _run_payload(value: SelectionRun) -> dict[str, object]:
    return _canonical_run_payload_impl(value)


def _canonical_run_hash(value: SelectionRun) -> str:
    return _canonical_run_hash_impl(value)


canonical_spec_hash = _canonical_spec_hash
canonical_input_hash = _canonical_input_hash
canonical_run_payload = _run_payload
canonical_run_hash = _canonical_run_hash
