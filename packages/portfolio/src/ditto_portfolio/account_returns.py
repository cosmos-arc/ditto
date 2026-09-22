"""
Pure money-precise time-weighted return linking over valuations and flows.

This module owns the numeric contract only: it receives already-built daily
total-value observations and classified external flows, splits sub-periods at
declared flow boundaries, links growth factors within continuous runs, and
breaks segments at valuation gaps, zero assets, and re-deposits.  Loading
prices, replaying ledgers, or deciding PIT visibility belongs to callers.

V1 rules (spec #249, first precise mode):

* Positive amounts are external inflows, negative are outflows.  Trades,
  dividends, interest, and fees are account-internal and must never appear
  here.
* A ``start_of_day`` flow joins the denominator of its day's leg
  (:math:`V_{close}/(V_{prev}+C)-1`); an ``end_of_day`` flow is removed from
  the leg's end value (:math:`(V_{close}-C)/V_{prev}-1`).  An ``intraday``
  flow lacks boundary valuations and fails that leg closed.  Legacy flows
  without a declared position fail with ``timing_unknown`` instead of
  guessing close-of-day.
* A loss to zero records a final ``-100%`` leg; a full redemption closes the
  segment with its pre-flow leg and never ``-100%``; re-deposits start a new
  segment instead of chaining across zero assets.
* Valuation gaps break linking: the next observation opens a fresh segment.
  Flows dated between observations (strictly inside the window) are a caller
  bug and fail closed; flows outside the window are ignored.
* No Modified Dietz or other approximation is ever produced.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from ditto_portfolio.account_ledger import FlowPosition
from ditto_portfolio.errors import PortfolioError

__all__ = [
    "RETURN_METHOD_VERSION",
    "ExternalFlow",
    "ExternalFlowKind",
    "ReturnPoint",
    "ReturnReason",
    "ReturnReasonCode",
    "ReturnSegment",
    "ReturnSeries",
    "SegmentClosedReason",
    "ValuationObservation",
    "compute_return_series",
]

RETURN_METHOD_VERSION = "twr-linked-v1"

_ONE = Decimal("1")
_ZERO = Decimal("0")


class ExternalFlowKind(StrEnum):
    """Whether a flow moved cash or non-cash assets across the boundary."""

    CASH = "cash"
    SECURITY_TRANSFER = "security_transfer"


class ReturnReasonCode(StrEnum):
    """Why a return value or segment link is absent."""

    TIMING_UNKNOWN = "timing_unknown"
    CASH_FLOW_VALUATION_MISSING = "cash_flow_valuation_missing"
    SECURITY_TRANSFER_UNSUPPORTED = "security_transfer_unsupported"
    NEGATIVE_EQUITY_UNSUPPORTED = "negative_equity_unsupported"
    VALUATION_GAP = "valuation_gap"
    FULL_WITHDRAWAL_SEGMENT_END = "full_withdrawal_segment_end"
    LOSS_TO_ZERO_SEGMENT_END = "loss_to_zero_segment_end"
    SINGLE_POINT_SEGMENT = "single_point_segment"
    NON_POSITIVE_BASE = "non_positive_base"


type SegmentClosedReason = Literal[
    "range_end",
    "loss_to_zero",
    "full_withdrawal",
    "valuation_gap",
    "negative_equity",
]


@dataclass(frozen=True, kw_only=True)
class ExternalFlow:
    """
    One signed external flow on a business date.

    ``amount`` is positive for inflows and negative for outflows; security
    transfers carry ``0`` and only mark their leg unsupported.
    """

    on_date: str
    amount: Decimal
    position: FlowPosition | None
    kind: ExternalFlowKind = ExternalFlowKind.CASH


@dataclass(frozen=True, kw_only=True)
class ValuationObservation:
    """One dated total-value point (assets plus cash, raw prices)."""

    on_date: str
    total_value: Decimal
    gap_before: bool = False


@dataclass(frozen=True, kw_only=True)
class ReturnReason:
    """One machine-readable absence cause."""

    code: ReturnReasonCode
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class ReturnPoint:
    """Per-observation value, flows, and nullable returns."""

    on_date: str
    total_value: Decimal
    external_flow: Decimal
    period_return: Decimal | None
    cumulative_return: Decimal | None
    segment_id: int | None
    reasons: tuple[ReturnReason, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ReturnSegment:
    """One continuous positive-capital run with its own linked TWR."""

    segment_id: int
    start_date: str
    end_date: str
    start_value: Decimal
    end_value: Decimal
    linked_return: Decimal | None
    closed_reason: SegmentClosedReason
    reasons: tuple[ReturnReason, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ReturnSeries:
    """Complete linked-result view for one account and range."""

    method: str
    points: tuple[ReturnPoint, ...]
    segments: tuple[ReturnSegment, ...]


@dataclass
class _SegmentState:
    segment_id: int
    start_date: str
    start_value: Decimal
    end_date: str
    end_value: Decimal
    factor: Decimal = _ONE
    known: bool = True
    point_count: int = 0
    closed_reason: SegmentClosedReason = "range_end"
    reasons: list[ReturnReason] = field(default_factory=list)

    def close(self, closed_reason: SegmentClosedReason) -> None:
        self.closed_reason = closed_reason

    def to_segment(self) -> ReturnSegment:
        return ReturnSegment(
            segment_id=self.segment_id,
            start_date=self.start_date,
            end_date=self.end_date,
            start_value=self.start_value,
            end_value=self.end_value,
            linked_return=self.factor - _ONE if self.known else None,
            closed_reason=self.closed_reason,
            reasons=tuple(self.reasons),
        )


def _net_cash_flow(flows: Sequence[ExternalFlow]) -> Decimal:
    return sum(
        (flow.amount for flow in flows if flow.kind is ExternalFlowKind.CASH),
        _ZERO,
    )


def _position_net(
    flows: Sequence[ExternalFlow],
    position: FlowPosition,
) -> Decimal:
    return sum(
        (
            flow.amount
            for flow in flows
            if flow.kind is ExternalFlowKind.CASH and flow.position is position
        ),
        _ZERO,
    )


def _leg_reasons(flows: Sequence[ExternalFlow]) -> list[ReturnReason]:
    reasons: list[ReturnReason] = []
    for flow in flows:
        if flow.kind is ExternalFlowKind.SECURITY_TRANSFER:
            reasons.append(
                ReturnReason(
                    code=ReturnReasonCode.SECURITY_TRANSFER_UNSUPPORTED,
                    detail=flow.on_date,
                )
            )
        elif flow.position is None:
            reasons.append(
                ReturnReason(code=ReturnReasonCode.TIMING_UNKNOWN, detail="")
            )
        elif flow.position is FlowPosition.INTRADAY:
            reasons.append(
                ReturnReason(
                    code=ReturnReasonCode.CASH_FLOW_VALUATION_MISSING,
                    detail="",
                )
            )
    return reasons


def _flows_by_date(
    flows: Iterable[ExternalFlow],
) -> dict[str, tuple[ExternalFlow, ...]]:
    grouped: dict[str, list[ExternalFlow]] = {}
    for flow in flows:
        grouped.setdefault(flow.on_date, []).append(flow)
    return {key: tuple(value) for key, value in grouped.items()}


def _validate_inputs(
    observations: tuple[ValuationObservation, ...],
    grouped_flows: dict[str, tuple[ExternalFlow, ...]],
) -> None:
    previous: str | None = None
    for observation in observations:
        if previous is not None and observation.on_date <= previous:
            raise PortfolioError(
                "return observations must be strictly increasing by date"
            )
        previous = observation.on_date
    if not observations or not grouped_flows:
        return
    dates = {observation.on_date for observation in observations}
    for on_date in grouped_flows:
        if on_date in dates or on_date < min(dates) or on_date > max(dates):
            continue
        raise PortfolioError(
            f"external flow date is not a valuation observation: {on_date}"
        )


def _try_open_segment(
    observation: ValuationObservation,
    today: Sequence[ExternalFlow],
    segment_id: int,
) -> _SegmentState | None:
    if observation.total_value <= _ZERO:
        return None
    base = observation.total_value - _position_net(today, FlowPosition.END_OF_DAY)
    if base <= _ZERO:
        return None
    return _SegmentState(
        segment_id=segment_id,
        start_date=observation.on_date,
        start_value=base,
        end_date=observation.on_date,
        end_value=observation.total_value,
    )


class _SeriesRunner:
    """Single-pass linking state machine over sorted observations."""

    def __init__(self) -> None:
        self.states: list[_SegmentState] = []
        self.points: list[ReturnPoint] = []
        self.open_segment: _SegmentState | None = None
        self.previous: ValuationObservation | None = None

    def step(
        self,
        observation: ValuationObservation,
        today: Sequence[ExternalFlow],
    ) -> None:
        """Process one observation as either a fresh run base or a linked leg."""
        starts_new_run = (
            self.previous is None
            or self.previous.total_value <= _ZERO
            or observation.gap_before
            or self.open_segment is None
        )
        if starts_new_run:
            self._start_run(observation, today)
        else:
            self._link_leg(observation, today)

    def finish(self) -> None:
        """Close any segment that survives to the range end."""
        if self.open_segment is not None:
            self.open_segment.close("range_end")

    def _start_run(
        self,
        observation: ValuationObservation,
        today: Sequence[ExternalFlow],
    ) -> None:
        if self.open_segment is not None:
            gap_reason = ReturnReason(
                code=ReturnReasonCode.VALUATION_GAP,
                detail=observation.on_date,
            )
            self.open_segment.close("valuation_gap")
            self.open_segment.reasons.append(gap_reason)
            self.open_segment = None
        segment = _try_open_segment(observation, today, len(self.states))
        if segment is None:
            self.points.append(_unbased_point(observation, today))
        else:
            self.states.append(segment)
            self.open_segment = segment
            segment.point_count += 1
            self.points.append(
                ReturnPoint(
                    on_date=observation.on_date,
                    total_value=observation.total_value,
                    external_flow=_net_cash_flow(today),
                    period_return=None,
                    cumulative_return=_ZERO,
                    segment_id=segment.segment_id,
                    reasons=(),
                )
            )
        self.previous = observation

    def _link_leg(
        self,
        observation: ValuationObservation,
        today: Sequence[ExternalFlow],
    ) -> None:
        segment = self.open_segment
        previous = self.previous
        if segment is None or previous is None:
            raise PortfolioError(
                "return linking requires an open segment and a prior observation"
            )
        segment.point_count += 1
        leg_reasons = _leg_reasons(today)
        base = previous.total_value + _position_net(today, FlowPosition.START_OF_DAY)
        end = observation.total_value - _position_net(today, FlowPosition.END_OF_DAY)
        period_return = self._apply_leg(segment, base, end, leg_reasons, observation)
        self._close_on_zero(segment, observation, end, base, leg_reasons)
        self.points.append(
            ReturnPoint(
                on_date=observation.on_date,
                total_value=observation.total_value,
                external_flow=_net_cash_flow(today),
                period_return=period_return,
                cumulative_return=segment.factor - _ONE if segment.known else None,
                segment_id=segment.segment_id,
                reasons=tuple(leg_reasons),
            )
        )
        if segment.closed_reason != "range_end":
            self.open_segment = None
        self.previous = observation

    def _apply_leg(
        self,
        segment: _SegmentState,
        base: Decimal,
        end: Decimal,
        leg_reasons: list[ReturnReason],
        observation: ValuationObservation,
    ) -> Decimal | None:
        if base == _ZERO:
            withdrawal_reason = ReturnReason(
                code=ReturnReasonCode.FULL_WITHDRAWAL_SEGMENT_END,
                detail=observation.on_date,
            )
            segment.known = False
            segment.reasons.append(withdrawal_reason)
            leg_reasons.append(withdrawal_reason)
            segment.close("full_withdrawal")
            return None
        if base < _ZERO or end < _ZERO:
            negative_reason = ReturnReason(
                code=ReturnReasonCode.NEGATIVE_EQUITY_UNSUPPORTED,
                detail=observation.on_date,
            )
            segment.known = False
            segment.reasons.append(negative_reason)
            leg_reasons.append(negative_reason)
            segment.close("negative_equity")
            return None
        if leg_reasons:
            segment.known = False
            return None
        period_return = end / base - _ONE
        segment.factor = segment.factor * (_ONE + period_return)
        return period_return

    def _close_on_zero(
        self,
        segment: _SegmentState,
        observation: ValuationObservation,
        end: Decimal,
        base: Decimal,
        leg_reasons: list[ReturnReason],
    ) -> None:
        segment.end_date = observation.on_date
        segment.end_value = observation.total_value
        if observation.total_value > _ZERO or segment.closed_reason != "range_end":
            return
        if end == _ZERO:
            closure_reason = ReturnReason(
                code=ReturnReasonCode.LOSS_TO_ZERO_SEGMENT_END,
                detail=observation.on_date,
            )
            segment.close("loss_to_zero")
        else:
            closure_reason = ReturnReason(
                code=ReturnReasonCode.FULL_WITHDRAWAL_SEGMENT_END,
                detail=observation.on_date,
            )
            segment.close("full_withdrawal")
        segment.reasons.append(closure_reason)
        leg_reasons.append(closure_reason)


def _unbased_point(
    observation: ValuationObservation,
    today: Sequence[ExternalFlow],
) -> ReturnPoint:
    if observation.total_value <= _ZERO:
        code = (
            ReturnReasonCode.NON_POSITIVE_BASE
            if observation.total_value < _ZERO
            else ReturnReasonCode.FULL_WITHDRAWAL_SEGMENT_END
        )
    else:
        code = ReturnReasonCode.FULL_WITHDRAWAL_SEGMENT_END
    return ReturnPoint(
        on_date=observation.on_date,
        total_value=observation.total_value,
        external_flow=_net_cash_flow(today),
        period_return=None,
        cumulative_return=None,
        segment_id=None,
        reasons=(ReturnReason(code=code, detail=observation.on_date),),
    )


def _freeze_segments(states: list[_SegmentState]) -> tuple[ReturnSegment, ...]:
    frozen: list[ReturnSegment] = []
    for state in states:
        if state.point_count == 1:
            state.reasons.append(
                ReturnReason(code=ReturnReasonCode.SINGLE_POINT_SEGMENT, detail="")
            )
            state.known = False
        frozen.append(state.to_segment())
    return tuple(frozen)


def compute_return_series(
    *,
    observations: tuple[ValuationObservation, ...],
    flows: tuple[ExternalFlow, ...],
) -> ReturnSeries:
    """Link sub-period growth factors into per-day and per-segment TWR."""
    grouped_flows = _flows_by_date(flows)
    _validate_inputs(observations, grouped_flows)
    runner = _SeriesRunner()
    for observation in observations:
        runner.step(observation, grouped_flows.get(observation.on_date, ()))
    runner.finish()
    return ReturnSeries(
        method=RETURN_METHOD_VERSION,
        points=tuple(runner.points),
        segments=_freeze_segments(runner.states),
    )
