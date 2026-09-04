"""Exact SelectionRun reads and deterministic previous-run comparison."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import SelectionRun
from ditto_strategy.selection.store import SelectionRunReader

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.selection_views import (
    SelectionRunView,
    to_selection_run_view,
)

__all__ = [
    "SelectionExclusionChange",
    "SelectionRankChange",
    "SelectionRunDiff",
    "SelectionRunQueryService",
]


@dataclass(frozen=True, slots=True)
class SelectionRankChange:
    """Rank movement for an instrument selected in both runs."""

    instrument_id: InstrumentId
    before_rank: int
    after_rank: int


@dataclass(frozen=True, slots=True)
class SelectionExclusionChange:
    """Why-in/why-out transition between two exact runs."""

    instrument_id: InstrumentId
    before_reason: str | None
    after_reason: str | None


@dataclass(frozen=True, slots=True)
class SelectionRunDiff:
    """Auditable diff that separates inputs from candidate outcome changes."""

    before_run_id: str
    after_run_id: str
    data_changed: bool
    industry_rotation_changed: bool
    spec_changed: bool
    seed_changed: bool
    added_candidate_ids: tuple[InstrumentId, ...]
    removed_candidate_ids: tuple[InstrumentId, ...]
    rank_changes: tuple[SelectionRankChange, ...]
    exclusion_changes: tuple[SelectionExclusionChange, ...]


def _reason_by_instrument(value: SelectionRun) -> dict[InstrumentId, str | None]:
    reasons: dict[InstrumentId, str | None] = {
        item.instrument_id: None for item in value.candidates
    }
    reasons.update(
        {item.instrument_id: item.reason_code.value for item in value.exclusions}
    )
    return reasons


class SelectionRunQueryService:
    """Read only exact saved runs; never reconstruct current-state approximations."""

    def __init__(self, reader: SelectionRunReader) -> None:
        self._reader = reader

    def _get_domain(self, run_id: str) -> SelectionRun:
        """Return one exact run or a typed query-boundary error."""
        if not run_id.strip():
            raise AppQueryError(
                "selection run_id must be non-empty",
                details={"reason": "invalid_selection_run_id"},
            )
        value = self._reader.get(run_id)
        if value is None:
            raise AppQueryError(
                f"selection run not found: {run_id}",
                details={"reason": "selection_run_not_found", "run_id": run_id},
            )
        return value

    def get(self, run_id: str) -> SelectionRunView:
        """Return one exact saved run as an application-owned read model."""
        return to_selection_run_view(self._get_domain(run_id))

    def list_by_spec(
        self, spec_id: str, *, limit: int = 100
    ) -> tuple[SelectionRunView, ...]:
        """List persisted runs for a spec without synthesizing filters."""
        if not spec_id.strip():
            raise AppQueryError(
                "selection spec_id must be non-empty",
                details={"reason": "invalid_selection_spec_id"},
            )
        if isinstance(limit, bool) or limit < 1:
            raise AppQueryError(
                "selection run limit must be a positive integer",
                details={"reason": "invalid_selection_run_limit"},
            )
        return tuple(
            to_selection_run_view(item)
            for item in self._reader.list_by_spec(spec_id, limit=limit)
        )

    def compare(self, before_run_id: str, after_run_id: str) -> SelectionRunDiff:
        """Compare two exact saved runs, including previous-run why-in/out changes."""
        if before_run_id == after_run_id:
            raise AppQueryError(
                "selection comparison requires distinct run IDs",
                details={"reason": "selection_compare_identical_runs"},
            )
        before = self._get_domain(before_run_id)
        after = self._get_domain(after_run_id)
        before_candidates = {item.instrument_id: item for item in before.candidates}
        after_candidates = {item.instrument_id: item for item in after.candidates}
        before_ids = set(before_candidates)
        after_ids = set(after_candidates)
        shared_ids = before_ids & after_ids
        rank_changes = tuple(
            SelectionRankChange(
                instrument_id=instrument_id,
                before_rank=before_candidates[instrument_id].rank,
                after_rank=after_candidates[instrument_id].rank,
            )
            for instrument_id in sorted(shared_ids)
            if before_candidates[instrument_id].rank
            != after_candidates[instrument_id].rank
        )
        before_reasons = _reason_by_instrument(before)
        after_reasons = _reason_by_instrument(after)
        exclusion_changes = tuple(
            SelectionExclusionChange(
                instrument_id=instrument_id,
                before_reason=before_reasons.get(instrument_id),
                after_reason=after_reasons.get(instrument_id),
            )
            for instrument_id in sorted(set(before_reasons) | set(after_reasons))
            if before_reasons.get(instrument_id) != after_reasons.get(instrument_id)
        )
        return SelectionRunDiff(
            before_run_id=before.run_id,
            after_run_id=after.run_id,
            data_changed=(
                before.source_snapshot_ids != after.source_snapshot_ids
                or before.universe_snapshot_id != after.universe_snapshot_id
            ),
            industry_rotation_changed=(
                before.industry_rotation_snapshot_id
                != after.industry_rotation_snapshot_id
            ),
            spec_changed=before.spec_hash != after.spec_hash,
            seed_changed=before.seed != after.seed,
            added_candidate_ids=tuple(sorted(after_ids - before_ids)),
            removed_candidate_ids=tuple(sorted(before_ids - after_ids)),
            rank_changes=rank_changes,
            exclusion_changes=exclusion_changes,
        )
