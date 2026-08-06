"""Exact PIT membership, warmup, and coverage-policy evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import cast

from ditto_application.research_certification_contracts import (
    is_canonical_content_hash,
    is_canonical_identity,
)
from ditto_application.research_validation_calendar import (
    CalendarMonth,
    canonical_payload_hash,
    fail_validation,
    require_exact_int,
    validate_calendar_month,
)

__all__ = [
    "CoverageEligibility",
    "InstrumentEligibilityEvidence",
    "IsolationSemantics",
    "MonthCoverageDecision",
    "PitUniverseMembershipInterval",
    "UniverseCoveragePolicy",
    "UniverseMembershipSource",
]

_MAX_COVERAGE_RATIO_BPS = 10_000
_MAX_MEMBERSHIP_INTERVALS_PER_INSTRUMENT = 16
_MAX_TOTAL_MEMBERSHIP_INTERVALS = 8_192


class CoverageEligibility(StrEnum):
    """A versioned coverage policy's decision for one complete month."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


def _validated_instrument_id_set(
    raw_ids: object,
    *,
    reason: str,
) -> tuple[str, ...]:
    if type(raw_ids) is not tuple:
        fail_validation("SPEC_INVALID", reason)
    ids = cast("tuple[object, ...]", raw_ids)
    if not all(is_canonical_identity(item) for item in ids) or len(set(ids)) != len(
        ids
    ):
        fail_validation("SPEC_INVALID", reason)
    return tuple(sorted(cast("tuple[str, ...]", ids)))


def instrument_id_set_hash(instrument_ids: tuple[str, ...]) -> str:
    """Return the canonical identity of one sorted instrument ID set."""
    return canonical_payload_hash({"instrument_ids": list(instrument_ids)})


@dataclass(frozen=True, slots=True)
class PitUniverseMembershipInterval:
    """Canonical inclusive month interval for one instrument's PIT membership."""

    start_month: CalendarMonth
    end_month: CalendarMonth

    def __post_init__(self) -> None:
        """Require exact, ordered inclusive month bounds."""
        start = validate_calendar_month(
            cast("object", self.start_month),
            reason="invalid_pit_membership_start_month",
        )
        end = validate_calendar_month(
            cast("object", self.end_month),
            reason="invalid_pit_membership_end_month",
        )
        if end < start:
            fail_validation("SPEC_INVALID", "pit_membership_interval_reversed")


def _validated_membership_intervals(
    raw_intervals: object,
    *,
    listing_date: date,
) -> tuple[PitUniverseMembershipInterval, ...]:
    if type(raw_intervals) is not tuple or not raw_intervals:
        fail_validation(
            "SPEC_INVALID", "pit_membership_intervals_must_be_non_empty_tuple"
        )
    typed_intervals = cast("tuple[object, ...]", raw_intervals)
    if len(typed_intervals) > _MAX_MEMBERSHIP_INTERVALS_PER_INSTRUMENT:
        fail_validation(
            "SPEC_INVALID",
            "MEMBERSHIP_EVIDENCE_TOO_LARGE",
            remediation="merge adjacent ranges or reduce PIT membership churn",
        )
    intervals: list[PitUniverseMembershipInterval] = []
    listing_month = CalendarMonth.from_date(listing_date)
    for raw_interval in typed_intervals:
        if type(raw_interval) is not PitUniverseMembershipInterval:
            fail_validation("SPEC_INVALID", "invalid_pit_membership_interval")
        interval = raw_interval
        start = validate_calendar_month(
            cast("object", interval.start_month),
            reason="invalid_pit_membership_start_month",
        )
        end = validate_calendar_month(
            cast("object", interval.end_month),
            reason="invalid_pit_membership_end_month",
        )
        if end < start:
            fail_validation("SPEC_INVALID", "pit_membership_interval_reversed")
        if start < listing_month:
            fail_validation("SPEC_INVALID", "pit_membership_precedes_listing_month")
        intervals.append(interval)
    for current, following in pairwise(intervals):
        if following.start_month <= current.end_month:
            fail_validation("SPEC_INVALID", "pit_membership_intervals_overlap")
        if following.start_month == current.end_month.next():
            fail_validation(
                "SPEC_INVALID", "adjacent_pit_membership_intervals_not_canonical"
            )
    return tuple(intervals)


@dataclass(frozen=True, slots=True)
class InstrumentEligibilityEvidence:
    """Per-instrument listing, certified-data, and warmup eligibility facts."""

    instrument_id: str
    listing_date: date
    base_data_eligible_start: date
    warmup_sessions: int
    eligible_from: date
    membership_intervals: tuple[PitUniverseMembershipInterval, ...]

    def __post_init__(self) -> None:
        """Reject ambiguous scalar evidence before calendar derivation."""
        if not is_canonical_identity(self.instrument_id):
            fail_validation("SPEC_INVALID", "invalid_instrument_eligibility_id")
        for field_name, value in (
            ("listing_date", self.listing_date),
            ("base_data_eligible_start", self.base_data_eligible_start),
            ("eligible_from", self.eligible_from),
        ):
            if type(value) is not date:
                fail_validation("SPEC_INVALID", f"invalid_instrument_{field_name}")
        require_exact_int(
            self.warmup_sessions,
            field_name="instrument_warmup_sessions",
            minimum=0,
        )
        _validated_membership_intervals(
            self.membership_intervals,
            listing_date=self.listing_date,
        )


@dataclass(frozen=True, slots=True)
class UniverseMembershipSource:
    """Certified source identity for one PIT universe membership projection."""

    universe_id: str
    dataset_id: str
    snapshot_id: str
    manifest_hash: str

    def __post_init__(self) -> None:
        """Require exact canonical source and universe identities."""
        if not all(
            is_canonical_identity(value)
            for value in (self.universe_id, self.dataset_id, self.snapshot_id)
        ) or not is_canonical_content_hash(self.manifest_hash):
            fail_validation("SPEC_INVALID", "invalid_membership_source_identity")


def _coverage_evaluator_hash(
    *,
    policy_id: str,
    version: int,
    min_eligible_instrument_count: int,
    min_coverage_ratio_bps: int,
) -> str:
    return canonical_payload_hash(
        {
            "evaluator": "pit-universe-eligible-coverage-v1",
            "policy_id": policy_id,
            "version": version,
            "min_eligible_instrument_count": min_eligible_instrument_count,
            "min_coverage_ratio_bps": min_coverage_ratio_bps,
        }
    )


@dataclass(frozen=True, slots=True)
class UniverseCoveragePolicy:
    """Explicit identity of the pre-registered universe coverage policy."""

    policy_id: str
    version: int
    min_eligible_instrument_count: int = 1
    min_coverage_ratio_bps: int = _MAX_COVERAGE_RATIO_BPS
    evaluator_hash: str = ""

    def __post_init__(self) -> None:
        """Require a stable non-empty identity and positive version."""
        if not is_canonical_identity(self.policy_id):
            fail_validation("SPEC_INVALID", "invalid_coverage_policy_id")
        require_exact_int(
            self.version,
            field_name="coverage_policy_version",
            minimum=1,
        )
        require_exact_int(
            self.min_eligible_instrument_count,
            field_name="min_eligible_instrument_count",
            minimum=1,
        )
        coverage_ratio = require_exact_int(
            self.min_coverage_ratio_bps,
            field_name="min_coverage_ratio_bps",
            minimum=0,
        )
        if coverage_ratio > _MAX_COVERAGE_RATIO_BPS:
            fail_validation("SPEC_INVALID", "invalid_min_coverage_ratio_bps")
        expected_hash = _coverage_evaluator_hash(
            policy_id=self.policy_id,
            version=self.version,
            min_eligible_instrument_count=self.min_eligible_instrument_count,
            min_coverage_ratio_bps=coverage_ratio,
        )
        if self.evaluator_hash == "":
            object.__setattr__(self, "evaluator_hash", expected_hash)
        elif self.evaluator_hash != expected_hash:
            fail_validation("SPEC_INVALID", "coverage_evaluator_hash_mismatch")


@dataclass(frozen=True, slots=True)
class MonthCoverageDecision:
    """Immutable policy evaluation bound to derived PIT membership identities."""

    month: CalendarMonth
    eligibility: CoverageEligibility
    universe_instrument_count: int
    universe_instrument_hash: str
    eligible_instrument_count: int
    eligible_instrument_hash: str

    def __post_init__(self) -> None:
        """Reject untyped, partial, or internally inconsistent decisions."""
        if type(self.month) is not CalendarMonth:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision_month")
        if type(self.eligibility) is not CoverageEligibility:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision_eligibility")
        for field_name, value in (
            ("universe_instrument_count", self.universe_instrument_count),
            ("eligible_instrument_count", self.eligible_instrument_count),
        ):
            require_exact_int(value, field_name=field_name, minimum=0)
        for field_name, value in (
            ("universe_instrument_hash", self.universe_instrument_hash),
            ("eligible_instrument_hash", self.eligible_instrument_hash),
        ):
            if not is_canonical_content_hash(value):
                fail_validation("SPEC_INVALID", f"invalid_{field_name}")
        if self.eligible_instrument_count > self.universe_instrument_count:
            fail_validation(
                "SPEC_INVALID", "eligible_instrument_count_exceeds_universe"
            )

    @classmethod
    def create(
        cls,
        *,
        month: CalendarMonth,
        eligibility: CoverageEligibility,
        universe_instrument_ids: tuple[str, ...],
        eligible_instrument_ids: tuple[str, ...],
    ) -> MonthCoverageDecision:
        """Bind one authority policy outcome to exact derived PIT ID sets."""
        universe_ids = _validated_instrument_id_set(
            universe_instrument_ids,
            reason="invalid_coverage_universe_instrument_ids",
        )
        eligible_ids = _validated_instrument_id_set(
            eligible_instrument_ids,
            reason="invalid_coverage_eligible_instrument_ids",
        )
        if not set(eligible_ids).issubset(universe_ids):
            fail_validation("SPEC_INVALID", "eligible_instruments_outside_pit_universe")
        return cls(
            month,
            eligibility,
            len(universe_ids),
            instrument_id_set_hash(universe_ids),
            len(eligible_ids),
            instrument_id_set_hash(eligible_ids),
        )


@dataclass(frozen=True, slots=True)
class IsolationSemantics:
    """Experiment-wide temporal semantics measured in trading sessions."""

    forward_horizon_sessions: int
    holding_period_sessions: int
    execution_lag_sessions: int

    def __post_init__(self) -> None:
        """Require non-negative, exact integer session counts."""
        for field_name, value in (
            ("forward_horizon_sessions", self.forward_horizon_sessions),
            ("holding_period_sessions", self.holding_period_sessions),
            ("execution_lag_sessions", self.execution_lag_sessions),
        ):
            require_exact_int(value, field_name=field_name, minimum=0)

    @property
    def width_sessions(self) -> int:
        """Return the purge/embargo width required by every split boundary."""
        return max(
            self.forward_horizon_sessions,
            self.holding_period_sessions,
            self.execution_lag_sessions,
        )


def validate_instrument_eligibility(  # noqa: C901, PLR0912 - fail-closed evidence fence
    raw_evidence: object,
    *,
    sessions: tuple[date, ...],
) -> tuple[InstrumentEligibilityEvidence, ...]:
    """Validate and canonicalize per-instrument calendar derivations."""
    if type(raw_evidence) is not tuple or not raw_evidence:
        fail_validation(
            "SPEC_INVALID", "instrument_eligibility_must_be_non_empty_tuple"
        )
    evidence: list[InstrumentEligibilityEvidence] = []
    total_intervals = 0
    for raw_item in cast("tuple[object, ...]", raw_evidence):
        if type(raw_item) is not InstrumentEligibilityEvidence:
            fail_validation("SPEC_INVALID", "invalid_instrument_eligibility_evidence")
        item = raw_item
        listing_date = item.listing_date
        data_start = item.base_data_eligible_start
        eligible_from = item.eligible_from
        if not is_canonical_identity(item.instrument_id):
            fail_validation("SPEC_INVALID", "invalid_instrument_eligibility_id")
        for reason, value in (
            ("invalid_instrument_listing_date", listing_date),
            ("invalid_instrument_base_data_eligible_start", data_start),
            ("invalid_instrument_eligible_from", eligible_from),
        ):
            if type(value) is not date:
                fail_validation("SPEC_INVALID", reason)
        warmup = require_exact_int(
            item.warmup_sessions,
            field_name="instrument_warmup_sessions",
            minimum=0,
        )
        _validated_membership_intervals(
            item.membership_intervals,
            listing_date=listing_date,
        )
        total_intervals += len(item.membership_intervals)
        if total_intervals > _MAX_TOTAL_MEMBERSHIP_INTERVALS:
            fail_validation(
                "SPEC_INVALID",
                "MEMBERSHIP_EVIDENCE_TOO_LARGE",
                remediation="reduce total PIT membership intervals below 8192",
            )
        listing_month = CalendarMonth.from_date(listing_date)
        calendar_first_month = CalendarMonth.from_date(sessions[0])
        calendar_last_month = CalendarMonth.from_date(sessions[-1])
        if listing_month > calendar_last_month:
            fail_validation("SPEC_INVALID", "listing_date_after_calendar_evidence")
        if calendar_first_month <= listing_month:
            listing_month_sessions = tuple(
                session
                for session in sessions
                if CalendarMonth.from_date(session) == listing_month
            )
            if listing_date not in listing_month_sessions:
                fail_validation("SPEC_INVALID", "listing_date_is_not_an_open_session")
            if listing_date != listing_month_sessions[0] and any(
                interval.start_month == listing_month
                for interval in item.membership_intervals
            ):
                fail_validation(
                    "SPEC_INVALID", "pit_membership_starts_in_partial_listing_month"
                )
        anchor = max(listing_date, data_start)
        eligible_sessions = tuple(session for session in sessions if session >= anchor)
        if len(eligible_sessions) <= warmup:
            fail_validation(
                "SPEC_INVALID",
                "instrument_warmup_not_covered_by_calendar",
                instrument_id=item.instrument_id,
            )
        expected = eligible_sessions[warmup]
        if eligible_from != expected:
            fail_validation(
                "SPEC_INVALID",
                "instrument_eligible_from_mismatch",
                instrument_id=item.instrument_id,
                expected=expected.isoformat(),
                observed=eligible_from.isoformat(),
            )
        evidence.append(item)
    if len({item.instrument_id for item in evidence}) != len(evidence):
        fail_validation("SPEC_INVALID", "duplicate_instrument_eligibility_evidence")
    return tuple(sorted(evidence, key=lambda item: item.instrument_id))


def validate_coverage_policy(raw_value: object) -> UniverseCoveragePolicy:
    """Revalidate one exact coverage-policy value object."""
    if type(raw_value) is not UniverseCoveragePolicy:
        fail_validation("SPEC_INVALID", "invalid_coverage_policy")
    if not is_canonical_identity(raw_value.policy_id):
        fail_validation("SPEC_INVALID", "invalid_coverage_policy_id")
    require_exact_int(
        raw_value.version,
        field_name="coverage_policy_version",
        minimum=1,
    )
    expected = UniverseCoveragePolicy(
        raw_value.policy_id,
        raw_value.version,
        raw_value.min_eligible_instrument_count,
        raw_value.min_coverage_ratio_bps,
        raw_value.evaluator_hash,
    )
    if expected != raw_value:
        fail_validation("SPEC_INVALID", "invalid_coverage_policy")
    return raw_value


def validate_isolation(raw_value: object) -> tuple[int, int, int]:
    """Return exact registered isolation scalars."""
    if type(raw_value) is not IsolationSemantics:
        fail_validation("SPEC_INVALID", "invalid_isolation_semantics")
    return (
        require_exact_int(
            raw_value.forward_horizon_sessions,
            field_name="forward_horizon_sessions",
            minimum=0,
        ),
        require_exact_int(
            raw_value.holding_period_sessions,
            field_name="holding_period_sessions",
            minimum=0,
        ),
        require_exact_int(
            raw_value.execution_lag_sessions,
            field_name="execution_lag_sessions",
            minimum=0,
        ),
    )


def validate_coverage_decisions(
    raw_decisions: object,
) -> dict[CalendarMonth, MonthCoverageDecision]:
    """Validate the exact ordered decision graph."""
    if type(raw_decisions) is not tuple:
        fail_validation("SPEC_INVALID", "coverage_decisions_must_be_tuple")
    typed: list[MonthCoverageDecision] = []
    for decision in cast("tuple[object, ...]", raw_decisions):
        if type(decision) is not MonthCoverageDecision:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision")
        validate_calendar_month(
            cast("object", decision.month),
            reason="invalid_coverage_decision_month",
        )
        if type(decision.eligibility) is not CoverageEligibility:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision_eligibility")
        require_exact_int(
            decision.universe_instrument_count,
            field_name="universe_instrument_count",
            minimum=0,
        )
        require_exact_int(
            decision.eligible_instrument_count,
            field_name="eligible_instrument_count",
            minimum=0,
        )
        if not is_canonical_content_hash(
            decision.universe_instrument_hash
        ) or not is_canonical_content_hash(decision.eligible_instrument_hash):
            fail_validation("SPEC_INVALID", "invalid_coverage_instrument_hash")
        if decision.eligible_instrument_count > decision.universe_instrument_count:
            fail_validation(
                "SPEC_INVALID", "eligible_instrument_count_exceeds_universe"
            )
        typed.append(decision)
    if any(current.month >= following.month for current, following in pairwise(typed)):
        fail_validation("SPEC_INVALID", "coverage_decisions_not_strictly_increasing")
    return {decision.month: decision for decision in typed}


def project_month_membership(
    *,
    month: CalendarMonth,
    first_session: date,
    instruments: tuple[InstrumentEligibilityEvidence, ...],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    set[tuple[str, CalendarMonth, CalendarMonth]],
]:
    """Derive one month's PIT and strategy-eligible membership identities."""
    consumed = {
        (item.instrument_id, interval.start_month, interval.end_month)
        for item in instruments
        for interval in item.membership_intervals
        if interval.start_month <= month <= interval.end_month
    }
    universe_ids = tuple(sorted({item[0] for item in consumed}))
    universe_id_set = set(universe_ids)
    eligible_ids = tuple(
        item.instrument_id
        for item in instruments
        if item.instrument_id in universe_id_set and item.eligible_from <= first_session
    )
    return universe_ids, eligible_ids, consumed


def _require_month_decision_identity(
    decision: MonthCoverageDecision,
    *,
    month: CalendarMonth,
    universe_ids: tuple[str, ...],
    eligible_ids: tuple[str, ...],
    policy: UniverseCoveragePolicy,
) -> None:
    identities_match = (
        decision.universe_instrument_count == len(universe_ids)
        and decision.universe_instrument_hash == instrument_id_set_hash(universe_ids)
        and decision.eligible_instrument_count == len(eligible_ids)
        and decision.eligible_instrument_hash == instrument_id_set_hash(eligible_ids)
    )
    if not identities_match:
        fail_validation(
            "SPEC_INVALID",
            "coverage_instrument_set_identity_mismatch",
            month=str(month),
        )
    derived_eligibility = (
        CoverageEligibility.ELIGIBLE
        if (
            len(eligible_ids) >= policy.min_eligible_instrument_count
            and bool(universe_ids)
            and len(eligible_ids) * _MAX_COVERAGE_RATIO_BPS
            >= len(universe_ids) * policy.min_coverage_ratio_bps
        )
        else CoverageEligibility.INELIGIBLE
    )
    if decision.eligibility is not derived_eligibility:
        fail_validation(
            "SPEC_INVALID",
            "coverage_policy_outcome_mismatch",
            month=str(month),
        )


def require_coverage_decisions(
    months: tuple[CalendarMonth, ...],
    decisions: dict[CalendarMonth, MonthCoverageDecision],
    *,
    instruments: tuple[InstrumentEligibilityEvidence, ...],
    session_months: dict[CalendarMonth, tuple[date, ...]],
    policy: UniverseCoveragePolicy,
) -> None:
    """Require exact decision domain and exact compiled month projections."""
    for month in months:
        if month not in decisions:
            fail_validation(
                "SPEC_INVALID", "coverage_decision_missing", month=str(month)
            )
    extra_months = sorted(set(decisions) - set(months))
    if extra_months:
        fail_validation(
            "SPEC_INVALID",
            "coverage_decision_outside_complete_month_domain",
            month=str(extra_months[0]),
        )
    observed_ids: set[str] = set()
    consumed_intervals: set[tuple[str, CalendarMonth, CalendarMonth]] = set()
    for month in months:
        universe_ids, eligible_ids, consumed = project_month_membership(
            month=month,
            first_session=session_months[month][0],
            instruments=instruments,
        )
        observed_ids.update(universe_ids)
        consumed_intervals.update(consumed)
        _require_month_decision_identity(
            decisions[month],
            month=month,
            universe_ids=universe_ids,
            eligible_ids=eligible_ids,
            policy=policy,
        )
    if observed_ids != {item.instrument_id for item in instruments}:
        fail_validation("SPEC_INVALID", "instrument_evidence_not_bound_to_pit_universe")
    expected_intervals = {
        (item.instrument_id, interval.start_month, interval.end_month)
        for item in instruments
        for interval in item.membership_intervals
    }
    if consumed_intervals != expected_intervals:
        fail_validation("SPEC_INVALID", "pit_membership_interval_not_consumed")


def continuous_eligible_suffix(
    complete_months: tuple[CalendarMonth, ...],
    decisions: dict[CalendarMonth, MonthCoverageDecision],
) -> tuple[tuple[CalendarMonth, ...], bool]:
    """Return the only continuous coverage-eligible trailing history."""
    suffix_start = len(complete_months)
    while (
        suffix_start > 0
        and decisions[complete_months[suffix_start - 1]].eligibility
        is CoverageEligibility.ELIGIBLE
    ):
        suffix_start -= 1
    return complete_months[suffix_start:], suffix_start > 0


def seal_instrument_eligibility(
    raw_evidence: object,
    *,
    sessions: tuple[date, ...],
) -> tuple[InstrumentEligibilityEvidence, ...]:
    """Read each untrusted field once and rebuild exact instrument evidence."""
    if type(raw_evidence) is not tuple:
        fail_validation("SPEC_INVALID", "instrument_eligibility_must_be_tuple")
    typed_evidence = cast("tuple[object, ...]", raw_evidence)
    sealed: list[InstrumentEligibilityEvidence] = []
    total_intervals = 0
    for raw_item in typed_evidence:
        if type(raw_item) is not InstrumentEligibilityEvidence:
            fail_validation("SPEC_INVALID", "invalid_instrument_eligibility_evidence")
        instrument_id = raw_item.instrument_id
        listing_date = raw_item.listing_date
        data_start = raw_item.base_data_eligible_start
        warmup = raw_item.warmup_sessions
        eligible_from = raw_item.eligible_from
        raw_intervals = raw_item.membership_intervals
        if type(raw_intervals) is not tuple:
            fail_validation("SPEC_INVALID", "invalid_pit_membership_intervals")
        if len(raw_intervals) > _MAX_MEMBERSHIP_INTERVALS_PER_INSTRUMENT:
            fail_validation(
                "SPEC_INVALID",
                "MEMBERSHIP_EVIDENCE_TOO_LARGE",
                remediation="merge adjacent ranges or reduce PIT membership churn",
            )
        total_intervals += len(raw_intervals)
        if total_intervals > _MAX_TOTAL_MEMBERSHIP_INTERVALS:
            fail_validation(
                "SPEC_INVALID",
                "MEMBERSHIP_EVIDENCE_TOO_LARGE",
                remediation="reduce total PIT membership intervals below 8192",
            )
        intervals: list[PitUniverseMembershipInterval] = []
        for raw_interval in raw_intervals:
            if type(raw_interval) is not PitUniverseMembershipInterval:
                fail_validation("SPEC_INVALID", "invalid_pit_membership_interval")
            raw_start = raw_interval.start_month
            raw_end = raw_interval.end_month
            if (
                type(raw_start) is not CalendarMonth
                or type(raw_end) is not CalendarMonth
            ):
                fail_validation("SPEC_INVALID", "invalid_pit_membership_interval")
            intervals.append(
                PitUniverseMembershipInterval(
                    CalendarMonth(raw_start.year, raw_start.month),
                    CalendarMonth(raw_end.year, raw_end.month),
                )
            )
        sealed.append(
            InstrumentEligibilityEvidence(
                instrument_id,
                listing_date,
                data_start,
                warmup,
                eligible_from,
                tuple(intervals),
            )
        )
    return validate_instrument_eligibility(tuple(sealed), sessions=sessions)


def seal_coverage_decisions(raw_decisions: object) -> tuple[MonthCoverageDecision, ...]:
    """Read each untrusted decision field once into exact immutable DTOs."""
    if type(raw_decisions) is not tuple:
        fail_validation("SPEC_INVALID", "coverage_decisions_must_be_tuple")
    typed_decisions = cast("tuple[object, ...]", raw_decisions)
    sealed: list[MonthCoverageDecision] = []
    for raw_decision in typed_decisions:
        if type(raw_decision) is not MonthCoverageDecision:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision")
        raw_month = raw_decision.month
        if type(raw_month) is not CalendarMonth:
            fail_validation("SPEC_INVALID", "invalid_coverage_decision_month")
        sealed.append(
            MonthCoverageDecision(
                CalendarMonth(raw_month.year, raw_month.month),
                raw_decision.eligibility,
                raw_decision.universe_instrument_count,
                raw_decision.universe_instrument_hash,
                raw_decision.eligible_instrument_count,
                raw_decision.eligible_instrument_hash,
            )
        )
    validate_coverage_decisions(tuple(sealed))
    return tuple(sealed)


def seal_coverage_policy(raw_value: object) -> UniverseCoveragePolicy:
    """Read one untrusted policy once into an exact value object."""
    if type(raw_value) is not UniverseCoveragePolicy:
        fail_validation("SPEC_INVALID", "invalid_coverage_policy")
    return UniverseCoveragePolicy(
        raw_value.policy_id,
        raw_value.version,
        raw_value.min_eligible_instrument_count,
        raw_value.min_coverage_ratio_bps,
        raw_value.evaluator_hash,
    )


def seal_isolation(raw_value: object) -> IsolationSemantics:
    """Read one untrusted isolation graph once into an exact value object."""
    if type(raw_value) is not IsolationSemantics:
        fail_validation("SPEC_INVALID", "invalid_isolation_semantics")
    return IsolationSemantics(
        raw_value.forward_horizon_sessions,
        raw_value.holding_period_sessions,
        raw_value.execution_lag_sessions,
    )
