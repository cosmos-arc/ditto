"""Execution planning for unified derived materialization."""

from __future__ import annotations

import math
from datetime import date, timedelta

from ditto_features.derived_types import DerivedSpec
from ditto_features.expression.contracts import CompiledDerivedExpression
from ditto_features.materialization.contracts import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
)
from ditto_features.materialization.models import DerivedRunMode

__all__ = ["DerivedExecutionPlanner"]


def _trading_days_to_calendar_days(trading_days: int) -> int:
    """
    Convert trading days to approximate calendar days.

    Uses fixed ratio 365/250 ~ 1.46 to account for weekends
    and approximate holidays.
    """
    return math.ceil(trading_days * 365 / 250)


class DerivedExecutionPlanner:
    """Resolve compute windows and partition targets for one run."""

    def plan(
        self,
        *,
        spec: DerivedSpec,
        compiled: CompiledDerivedExpression,
        request: DerivedMaterializationRequest,
        earliest_pending_invalidation_start: str | None = None,
    ) -> DerivedExecutionPlan:
        """Build a profile-aware execution plan."""
        anchor_start = request.request_start
        if (
            request.mode == DerivedRunMode.INCREMENTAL
            and earliest_pending_invalidation_start is not None
            and earliest_pending_invalidation_start < anchor_start
        ):
            anchor_start = earliest_pending_invalidation_start

        compute_start = anchor_start
        if (
            request.mode == DerivedRunMode.INCREMENTAL
            and compiled.analysis.lookback > 0
        ):
            calendar_lookback = _trading_days_to_calendar_days(
                compiled.analysis.lookback,
            )
            compute_start = (
                date.fromisoformat(anchor_start) - timedelta(days=calendar_lookback)
            ).isoformat()

        partitions = _partition_years(request.request_start, request.request_end)
        return DerivedExecutionPlan(
            derived_id=spec.id,
            version=spec.version,
            profile=spec.materialization_profile,
            mode=request.mode,
            request_start=request.request_start,
            request_end=request.request_end,
            compute_start=compute_start,
            compute_end=request.request_end,
            partitions=partitions,
            lookback=compiled.analysis.lookback,
            requires_full_day=compiled.analysis.requires_full_day,
        )


def _partition_years(start: str, end: str) -> tuple[str, ...]:
    """Return durable yearly partition keys covering the request window."""
    start_year = date.fromisoformat(start).year
    end_year = date.fromisoformat(end).year
    return tuple(str(year) for year in range(start_year, end_year + 1))
