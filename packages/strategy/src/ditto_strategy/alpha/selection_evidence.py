"""Strategy-owned contracts for auditable selection evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite
from typing import Protocol, cast

__all__ = [
    "ExclusionEvidence",
    "ExclusionReason",
    "FactorContributionEvidence",
    "InitialUniverseEvidence",
    "SelectionEvidence",
    "SelectionEvidenceCollector",
    "SelectionEvidenceLog",
    "SelectionEvidenceSink",
]

type EvidenceInstrumentId = int | str


def _validate_instrument_id(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("instrument_id must be a non-boolean int or non-empty str")
    if isinstance(value, str) and not value:
        raise ValueError("instrument_id must be a non-empty str")


def _validate_positive_int(value: object, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_text(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _validate_reason_code(value: object) -> None:
    if not isinstance(value, ExclusionReason):
        raise TypeError("reason_code must be ExclusionReason")


def _validate_optional_message(value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError("message must be display text or None")


def _validate_optional_bool(value: object, *, field_name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool or None")


def _validate_bool(value: object, *, field_name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _validate_finite_number(
    value: object,
    *,
    field_name: str,
    optional: bool = False,
) -> None:
    if value is None and optional:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a finite number")
    if not isfinite(float(value)):
        raise ValueError(f"{field_name} must be a finite number")


def _copy_ordered_events[EventT](
    value: object,
    *,
    event_type: type[EventT],
    field_name: str,
) -> tuple[EventT, ...]:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an ordered sequence")
    copied: list[EventT] = []
    for event in cast("Sequence[object]", value):
        if not isinstance(event, event_type):
            raise TypeError(f"{field_name} must contain only {event_type.__name__}")
        copied.append(event)
    return tuple(copied)


class ExclusionReason(StrEnum):
    """Stable machine-readable reasons for leaving the candidate pool."""

    MISSING_DATA = "missing_data"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    ST_STATUS = "st_status"
    SUSPENDED = "suspended"
    RISK_LOCKED = "risk_locked"
    TREND_THRESHOLD = "trend_threshold"
    CONDITION_NOT_MET = "condition_not_met"
    BELOW_TOP_K = "below_top_k"


@dataclass(frozen=True, slots=True)
class InitialUniverseEvidence:
    """One instrument entering the pipeline before joins or stages."""

    instrument_id: EvidenceInstrumentId
    ordinal: int

    def __post_init__(self) -> None:
        """Validate immutable universe evidence at its public boundary."""
        _validate_instrument_id(self.instrument_id)
        _validate_positive_int(self.ordinal, field_name="ordinal")


@dataclass(frozen=True, slots=True)
class ExclusionEvidence:
    """The first stage and stable reason that excluded one instrument."""

    instrument_id: EvidenceInstrumentId
    stage: str
    reason_code: ExclusionReason
    message: str | None = None

    def __post_init__(self) -> None:
        """Validate immutable exclusion evidence at its public boundary."""
        _validate_instrument_id(self.instrument_id)
        _validate_text(self.stage, field_name="stage")
        _validate_reason_code(self.reason_code)
        _validate_optional_message(self.message)


@dataclass(frozen=True, slots=True)
class FactorContributionEvidence:
    """One factor's values and contribution to an instrument's score."""

    instrument_id: EvidenceInstrumentId
    factor_name: str
    raw_value: float | None
    processed_value: float | None
    normalized_value: float | None
    weight: float
    contribution: float | None
    score: float | None
    rank: int | None = None
    selected: bool | None = None

    def __post_init__(self) -> None:
        """Validate all numeric contribution fields and optional state."""
        _validate_instrument_id(self.instrument_id)
        _validate_text(self.factor_name, field_name="factor_name")
        _validate_finite_number(
            self.raw_value,
            field_name="raw_value",
            optional=True,
        )
        _validate_finite_number(
            self.processed_value,
            field_name="processed_value",
            optional=True,
        )
        _validate_finite_number(
            self.normalized_value,
            field_name="normalized_value",
            optional=True,
        )
        _validate_finite_number(self.weight, field_name="weight")
        _validate_finite_number(
            self.contribution,
            field_name="contribution",
            optional=True,
        )
        _validate_finite_number(self.score, field_name="score", optional=True)
        if self.rank is not None:
            _validate_positive_int(self.rank, field_name="rank")
        _validate_optional_bool(self.selected, field_name="selected")


@dataclass(frozen=True, slots=True)
class SelectionEvidence:
    """Top-k decision for one instrument in selector output order."""

    instrument_id: EvidenceInstrumentId
    score: float | None
    rank: int
    selected: bool

    def __post_init__(self) -> None:
        """Validate immutable top-k selection evidence."""
        _validate_instrument_id(self.instrument_id)
        _validate_finite_number(self.score, field_name="score", optional=True)
        _validate_positive_int(self.rank, field_name="rank")
        _validate_bool(self.selected, field_name="selected")


type SelectionEvidenceEvent = (
    InitialUniverseEvidence
    | ExclusionEvidence
    | FactorContributionEvidence
    | SelectionEvidence
)


class SelectionEvidenceSink(Protocol):
    """Narrow side-channel used by stages to emit immutable evidence."""

    def emit(self, event: SelectionEvidenceEvent) -> None:
        """Accept one evidence event or raise to the caller."""
        ...


@dataclass(frozen=True, slots=True)
class SelectionEvidenceLog:
    """Immutable snapshot of all evidence emitted by one pipeline run."""

    initial_universe: tuple[InitialUniverseEvidence, ...] = ()
    exclusions: tuple[ExclusionEvidence, ...] = ()
    factor_contributions: tuple[FactorContributionEvidence, ...] = ()
    selections: tuple[SelectionEvidence, ...] = ()

    def __post_init__(self) -> None:
        """Defensively copy every ordered event sequence into tuples."""
        object.__setattr__(
            self,
            "initial_universe",
            _copy_ordered_events(
                self.initial_universe,
                event_type=InitialUniverseEvidence,
                field_name="initial_universe",
            ),
        )
        object.__setattr__(
            self,
            "exclusions",
            _copy_ordered_events(
                self.exclusions,
                event_type=ExclusionEvidence,
                field_name="exclusions",
            ),
        )
        object.__setattr__(
            self,
            "factor_contributions",
            _copy_ordered_events(
                self.factor_contributions,
                event_type=FactorContributionEvidence,
                field_name="factor_contributions",
            ),
        )
        object.__setattr__(
            self,
            "selections",
            _copy_ordered_events(
                self.selections,
                event_type=SelectionEvidence,
                field_name="selections",
            ),
        )


class SelectionEvidenceCollector:
    """In-memory sink that publishes immutable snapshots."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[SelectionEvidenceEvent] = []

    def emit(self, event: object) -> None:
        """Accept one event."""
        if not isinstance(
            event,
            InitialUniverseEvidence
            | ExclusionEvidence
            | FactorContributionEvidence
            | SelectionEvidence,
        ):
            raise TypeError("event must be an immutable selection evidence record")
        self._events.append(event)

    def snapshot(self) -> SelectionEvidenceLog:
        """Return an immutable snapshot."""
        initial_universe = tuple(
            event
            for event in self._events
            if isinstance(event, InitialUniverseEvidence)
        )
        exclusions = tuple(
            event for event in self._events if isinstance(event, ExclusionEvidence)
        )
        selections = tuple(
            event for event in self._events if isinstance(event, SelectionEvidence)
        )
        selection_by_instrument = {event.instrument_id: event for event in selections}
        factor_contributions = tuple(
            _enrich_contribution(event, selection_by_instrument)
            for event in self._events
            if isinstance(event, FactorContributionEvidence)
        )
        return SelectionEvidenceLog(
            initial_universe=initial_universe,
            exclusions=exclusions,
            factor_contributions=factor_contributions,
            selections=selections,
        )


def _enrich_contribution(
    event: FactorContributionEvidence,
    selections: dict[EvidenceInstrumentId, SelectionEvidence],
) -> FactorContributionEvidence:
    selection = selections.get(event.instrument_id)
    if selection is None:
        return event
    return replace(event, rank=selection.rank, selected=selection.selected)
