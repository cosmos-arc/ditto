"""Strategy-owned contracts for auditable selection evidence."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from math import isfinite
from typing import Protocol, cast

from ditto_strategy.errors import StrategySpecError

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
type EvidenceKey = tuple[str, EvidenceInstrumentId]


def _evidence_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> StrategySpecError:
    payload: dict[str, object] = {"reason": reason}
    payload.update(details)
    return StrategySpecError(message, details=payload)


def _validate_trade_date(value: object) -> None:
    if not isinstance(value, str):
        raise _evidence_error(
            "selection evidence trade_date must be an ISO date",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _evidence_error(
            "selection evidence trade_date must be an ISO date",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        ) from exc
    if parsed.isoformat() != value:
        raise _evidence_error(
            "selection evidence trade_date must use YYYY-MM-DD",
            reason="invalid_evidence_trade_date",
            trade_date=value,
        )


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

    trade_date: str
    instrument_id: EvidenceInstrumentId
    ordinal: int

    def __post_init__(self) -> None:
        """Validate immutable universe evidence at its public boundary."""
        _validate_trade_date(self.trade_date)
        _validate_instrument_id(self.instrument_id)
        _validate_positive_int(self.ordinal, field_name="ordinal")


@dataclass(frozen=True, slots=True)
class ExclusionEvidence:
    """The first stage and stable reason that excluded one instrument."""

    trade_date: str
    instrument_id: EvidenceInstrumentId
    stage: str
    reason_code: ExclusionReason
    message: str | None = None

    def __post_init__(self) -> None:
        """Validate immutable exclusion evidence at its public boundary."""
        _validate_trade_date(self.trade_date)
        _validate_instrument_id(self.instrument_id)
        _validate_text(self.stage, field_name="stage")
        _validate_reason_code(self.reason_code)
        _validate_optional_message(self.message)


@dataclass(frozen=True, slots=True)
class FactorContributionEvidence:
    """One factor's additive contribution to its factor-stage signal score."""

    trade_date: str
    instrument_id: EvidenceInstrumentId
    factor_name: str
    raw_value: float | None
    processed_value: float | None
    normalized_value: float | None
    weight: float
    contribution: float | None
    factor_signal_score: float | None
    rank: int | None = None
    selected: bool | None = None

    def __post_init__(self) -> None:
        """Validate all numeric contribution fields and optional state."""
        _validate_trade_date(self.trade_date)
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
        _validate_finite_number(
            self.factor_signal_score,
            field_name="factor_signal_score",
            optional=True,
        )
        if self.rank is not None:
            _validate_positive_int(self.rank, field_name="rank")
        _validate_optional_bool(self.selected, field_name="selected")


@dataclass(frozen=True, slots=True)
class SelectionEvidence:
    """Top-k decision for one instrument in selector output order."""

    trade_date: str
    instrument_id: EvidenceInstrumentId
    score: float | None
    rank: int
    selected: bool

    def __post_init__(self) -> None:
        """Validate immutable top-k selection evidence."""
        _validate_trade_date(self.trade_date)
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

    def begin_rebalance(self, trade_date: str) -> None:
        """Bind subsequent events to one validated rebalance date."""
        ...

    def commit_rebalance(self) -> None:
        """Publish every event in the active rebalance atomically."""
        ...

    def abort_rebalance(self) -> None:
        """Discard every event in the active rebalance."""
        ...

    @property
    def current_trade_date(self) -> str:
        """Return the active date or fail closed when no run is bound."""
        ...

    def emit(self, event: SelectionEvidenceEvent) -> None:
        """Accept one evidence event or raise to the caller."""
        ...


@dataclass(frozen=True, slots=True)
class SelectionEvidenceLog:
    """Immutable snapshot of evidence from one or more rebalance dates."""

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
        _validate_event_invariants(
            (
                *self.initial_universe,
                *self.exclusions,
                *self.factor_contributions,
                *self.selections,
            ),
        )


class SelectionEvidenceCollector:
    """In-memory sink that publishes immutable snapshots."""

    __slots__ = (
        "_contribution_keys",
        "_current_trade_date",
        "_events",
        "_exclusion_keys",
        "_initial_keys",
        "_pending_events",
        "_selections",
    )

    def __init__(self) -> None:
        self._events: list[SelectionEvidenceEvent] = []
        self._pending_events: list[SelectionEvidenceEvent] = []
        self._current_trade_date: str | None = None
        self._initial_keys: set[EvidenceKey] = set()
        self._exclusion_keys: set[EvidenceKey] = set()
        self._contribution_keys: set[tuple[str, EvidenceInstrumentId, str]] = set()
        self._selections: dict[EvidenceKey, SelectionEvidence] = {}

    def begin_rebalance(self, trade_date: str) -> None:
        """Bind this reusable collector to the next pipeline rebalance date."""
        _validate_trade_date(trade_date)
        if self._current_trade_date is not None:
            raise _evidence_error(
                "selection evidence sink already has an active rebalance",
                reason="evidence_rebalance_already_active",
                active_trade_date=self._current_trade_date,
                requested_trade_date=trade_date,
            )
        self._current_trade_date = trade_date

    def commit_rebalance(self) -> None:
        """Publish the active batch after its TargetPortfolio is constructed."""
        self._require_active_rebalance()
        self._events.extend(self._pending_events)
        self._pending_events.clear()
        self._current_trade_date = None

    def abort_rebalance(self) -> None:
        """Rollback the active batch and every incremental index entry."""
        self._require_active_rebalance()
        for event in reversed(self._pending_events):
            self._remove_from_indexes(event)
        self._pending_events.clear()
        self._current_trade_date = None

    def _require_active_rebalance(self) -> None:
        if self._current_trade_date is None:
            raise _evidence_error(
                "selection evidence sink is not bound to a rebalance date",
                reason="evidence_rebalance_unbound",
            )

    @property
    def current_trade_date(self) -> str:
        """Return the active date, rejecting direct unbound stage emission."""
        if self._current_trade_date is None:
            raise _evidence_error(
                "selection evidence sink is not bound to a rebalance date",
                reason="evidence_rebalance_unbound",
            )
        return self._current_trade_date

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
        active_trade_date = self.current_trade_date
        if event.trade_date != active_trade_date:
            raise _evidence_error(
                "selection evidence trade_date does not match active rebalance",
                reason="evidence_trade_date_mismatch",
                active_trade_date=active_trade_date,
                event_trade_date=event.trade_date,
            )
        self._validate_incremental_event(event)
        self._add_to_indexes(event)
        self._pending_events.append(event)

    def _validate_incremental_event(self, event: SelectionEvidenceEvent) -> None:
        """Validate one event against date-keyed O(1) indexes."""
        key = (event.trade_date, event.instrument_id)
        if isinstance(event, InitialUniverseEvidence):
            _require_unique_key(
                key,
                seen=self._initial_keys,
                evidence_kind="initial universe",
            )
            return
        if isinstance(event, ExclusionEvidence):
            _require_unique_key(
                key,
                seen=self._exclusion_keys,
                evidence_kind="exclusion",
            )
            selection = self._selections.get(key)
            if selection is not None and selection.selected:
                raise _contradictory_exclusion_error(key)
            return
        if isinstance(event, FactorContributionEvidence):
            contribution_key = (*key, event.factor_name)
            if contribution_key in self._contribution_keys:
                raise _duplicate_contribution_error(event)
            return
        _require_unique_key(
            key,
            seen=self._selections,
            evidence_kind="selection",
        )
        if event.selected and key in self._exclusion_keys:
            raise _contradictory_exclusion_error(key)

    def _add_to_indexes(self, event: SelectionEvidenceEvent) -> None:
        key = (event.trade_date, event.instrument_id)
        if isinstance(event, InitialUniverseEvidence):
            self._initial_keys.add(key)
        elif isinstance(event, ExclusionEvidence):
            self._exclusion_keys.add(key)
        elif isinstance(event, FactorContributionEvidence):
            self._contribution_keys.add((*key, event.factor_name))
        else:
            self._selections[key] = event

    def _remove_from_indexes(self, event: SelectionEvidenceEvent) -> None:
        key = (event.trade_date, event.instrument_id)
        if isinstance(event, InitialUniverseEvidence):
            self._initial_keys.remove(key)
        elif isinstance(event, ExclusionEvidence):
            self._exclusion_keys.remove(key)
        elif isinstance(event, FactorContributionEvidence):
            self._contribution_keys.remove((*key, event.factor_name))
        else:
            del self._selections[key]

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
        selection_by_instrument = {
            (event.trade_date, event.instrument_id): event for event in selections
        }
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
    selections: dict[EvidenceKey, SelectionEvidence],
) -> FactorContributionEvidence:
    selection = selections.get((event.trade_date, event.instrument_id))
    if selection is None:
        return event
    return replace(event, rank=selection.rank, selected=selection.selected)


def _validate_event_invariants(events: Sequence[SelectionEvidenceEvent]) -> None:
    """Reject ambiguous same-day evidence before enrichment or serialization."""
    initial_keys: set[EvidenceKey] = set()
    exclusion_keys: set[EvidenceKey] = set()
    contribution_keys: set[tuple[str, EvidenceInstrumentId, str]] = set()
    selections: dict[EvidenceKey, SelectionEvidence] = {}
    for event in events:
        key = (event.trade_date, event.instrument_id)
        if isinstance(event, InitialUniverseEvidence):
            _require_unique_key(
                key,
                seen=initial_keys,
                evidence_kind="initial universe",
            )
            initial_keys.add(key)
            continue
        if isinstance(event, ExclusionEvidence):
            _require_unique_key(
                key,
                seen=exclusion_keys,
                evidence_kind="exclusion",
            )
            selection = selections.get(key)
            if selection is not None and selection.selected:
                raise _contradictory_exclusion_error(key)
            exclusion_keys.add(key)
            continue
        if isinstance(event, FactorContributionEvidence):
            contribution_key = (*key, event.factor_name)
            if contribution_key in contribution_keys:
                raise _duplicate_contribution_error(event)
            contribution_keys.add(contribution_key)
            continue
        _require_unique_key(
            key,
            seen=selections,
            evidence_kind="selection",
        )
        if event.selected and key in exclusion_keys:
            raise _contradictory_exclusion_error(key)
        selections[key] = event


def _require_unique_key(
    key: EvidenceKey,
    *,
    seen: Collection[EvidenceKey],
    evidence_kind: str,
) -> None:
    if key not in seen:
        return
    trade_date, instrument_id = key
    raise _evidence_error(
        f"duplicate {evidence_kind} evidence for one instrument and trade_date",
        reason=f"duplicate_{evidence_kind.replace(' ', '_')}_evidence",
        trade_date=trade_date,
        instrument_id=instrument_id,
    )


def _duplicate_contribution_error(
    event: FactorContributionEvidence,
) -> StrategySpecError:
    return _evidence_error(
        "duplicate factor contribution evidence for instrument/factor/date",
        reason="duplicate_factor_contribution_evidence",
        trade_date=event.trade_date,
        instrument_id=event.instrument_id,
        factor_name=event.factor_name,
    )


def _contradictory_exclusion_error(key: EvidenceKey) -> StrategySpecError:
    trade_date, instrument_id = key
    return _evidence_error(
        "selected instrument has contradictory exclusion evidence",
        reason="contradictory_exclusion_evidence",
        trade_date=trade_date,
        instrument_id=instrument_id,
    )
