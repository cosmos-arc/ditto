"""
Pure common-window comparison over per-leg flow-adjusted return series.

Each leg (Model/Paper/Manual) contributes dated valuations with segment
identities and nullable period returns. A common window run starts at the
first date all legs value, continues only while every leg stays inside one
of its own segments with computable per-day returns, and never links across
a gap, a re-funding segment, or an unknown flow-timing break. Every run is
normalized to 1 at its own start; a single-point run reports assets only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from ditto_portfolio.errors import PortfolioError

__all__ = [
    "COMMON_WINDOW_POLICY_VERSION",
    "WindowComparison",
    "WindowLeg",
    "WindowLegPoint",
    "WindowRun",
    "WindowRunPoint",
    "compare_common_windows",
]

COMMON_WINDOW_POLICY_VERSION = "common-window-twr-v1"

_ONE = Decimal("1")
_MIN_LEGS = 2


@dataclass(frozen=True, kw_only=True)
class WindowLegPoint:
    """One dated leg row; gap days carry null value/segment/return."""

    on_date: str
    total_value: Decimal | None
    period_return: Decimal | None
    segment_id: int | None


@dataclass(frozen=True, kw_only=True)
class WindowLeg:
    """One leg's dated rows in the compared range."""

    kind: str
    points: tuple[WindowLegPoint, ...]


@dataclass(frozen=True, kw_only=True)
class WindowRunPoint:
    """One common date inside one run."""

    on_date: str
    growth: Mapping[str, Decimal]
    assets: Mapping[str, Decimal]


@dataclass(frozen=True, kw_only=True)
class WindowRun:
    """One maximal common continuous run, anchored to 1 at its start."""

    start_date: str
    end_date: str
    points: tuple[WindowRunPoint, ...]
    window_returns: Mapping[str, Decimal | None]


@dataclass(frozen=True, kw_only=True)
class WindowComparison:
    """Common-window outcome; incomparability is explicit, never an error."""

    status: str
    empty_reason: str | None
    runs: tuple[WindowRun, ...]


def _asset(point: WindowLegPoint) -> Decimal:
    if point.total_value is None:
        raise PortfolioError(
            f"point on {point.on_date} must be valued inside a common run"
        )
    return point.total_value


def _valued(point: WindowLegPoint) -> bool:
    return (
        point.segment_id is not None
        and point.total_value is not None
        and point.total_value > 0
    )


def _points_by_date(leg: WindowLeg) -> dict[str, WindowLegPoint]:
    points: dict[str, WindowLegPoint] = {}
    for point in leg.points:
        if point.on_date in points:
            raise PortfolioError(
                f"leg {leg.kind} has duplicate points on {point.on_date}"
            )
        points[point.on_date] = point
    return points


def _stretch_growth(
    points: Mapping[str, WindowLegPoint],
    dates: Sequence[str],
    *,
    previous: str,
    current: str,
) -> Decimal | None:
    """
    Link one leg's growth across ``previous`` → ``current``.

    The stretch is linkable only when every leg row in ``(previous, current]``
    stays in the segment open at ``previous`` with a computable per-day
    return; gaps, re-funding segments, and unknown flow timing break it.
    """
    anchor = points[previous]
    if not _valued(anchor):
        return None
    factor = _ONE
    for day in dates:
        if day <= previous:
            continue
        if day > current:
            break
        point = points[day]
        if not _valued(point) or point.segment_id != anchor.segment_id:
            return None
        if point.period_return is None:
            return None
        factor = factor * (_ONE + point.period_return)
    return factor


def _run_point(
    day: str,
    growth: Mapping[str, Decimal],
    by_kind: Mapping[str, Mapping[str, WindowLegPoint]],
    kinds: Sequence[str],
) -> WindowRunPoint:
    return WindowRunPoint(
        on_date=day,
        growth=dict(growth),
        assets={kind: _asset(by_kind[kind][day]) for kind in kinds},
    )


def _build_run(points: Sequence[WindowRunPoint], kinds: Sequence[str]) -> WindowRun:
    if len(points) > 1:
        returns = {kind: points[-1].growth[kind] - _ONE for kind in kinds}
    else:
        returns = dict.fromkeys(kinds)
    return WindowRun(
        start_date=points[0].on_date,
        end_date=points[-1].on_date,
        points=tuple(points),
        window_returns=returns,
    )


def compare_common_windows(legs: Sequence[WindowLeg]) -> WindowComparison:
    """Compute maximal common continuous runs across two or more legs."""
    if len(legs) < _MIN_LEGS:
        raise PortfolioError("common window comparison requires at least two legs")
    kinds = [leg.kind for leg in legs]
    if len(set(kinds)) != len(kinds):
        raise PortfolioError("leg kinds must be unique")

    by_kind = {leg.kind: _points_by_date(leg) for leg in legs}
    dates_by_kind = {kind: sorted(by_kind[kind]) for kind in kinds}
    valued_sets = [
        {day for day in by_kind[kind] if _valued(by_kind[kind][day])} for kind in kinds
    ]
    common_dates = sorted(valued_sets[0].intersection(*valued_sets[1:]))
    if not common_dates:
        return WindowComparison(
            status="incomparable",
            empty_reason="no_common_valuation_dates",
            runs=(),
        )

    def stretch(kind: str, previous: str, current: str) -> Decimal | None:
        return _stretch_growth(
            by_kind[kind], dates_by_kind[kind], previous=previous, current=current
        )

    ones = dict.fromkeys(kinds, _ONE)
    runs: list[WindowRun] = []
    growth = dict(ones)
    run_points = [_run_point(common_dates[0], growth, by_kind, kinds)]
    for previous, current in pairwise(common_dates):
        factors = {kind: stretch(kind, previous, current) for kind in kinds}
        linked = {
            kind: factor for kind, factor in factors.items() if factor is not None
        }
        if len(linked) == len(kinds):
            growth = {kind: growth[kind] * linked[kind] for kind in kinds}
            run_points.append(_run_point(current, growth, by_kind, kinds))
            continue
        runs.append(_build_run(run_points, kinds))
        growth = dict(ones)
        run_points = [_run_point(current, growth, by_kind, kinds)]
    runs.append(_build_run(run_points, kinds))

    status = (
        "comparable"
        if any(len(run.points) > 1 for run in runs)
        else "single_common_point"
    )
    return WindowComparison(status=status, empty_reason=None, runs=tuple(runs))
