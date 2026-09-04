"""Create an immutable Analysis Research Case from one exact SelectionRun."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import SelectionRunStatus
from ditto_strategy.selection.identity import canonical_selection_run_hash
from ditto_strategy.selection.store import SelectionRunReader

from ditto_application.exceptions import AppProcessError
from ditto_application.research_case_contracts import (
    ResearchCaseFactory,
    ResearchCaseMaterial,
    ResearchCaseView,
)

__all__ = ["CreateResearchCaseFromSelection", "CreateResearchCaseRequest"]


@dataclass(frozen=True, slots=True)
class CreateResearchCaseRequest:
    """User hypothesis and optional ranked candidate subset."""

    selection_run_id: str
    objective: str
    candidate_instrument_ids: tuple[InstrumentId, ...] = ()


def _error(message: str, *, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(message, details={"reason": reason, **details})


class CreateResearchCaseFromSelection:
    """Bind a Research Case to persisted selection evidence without latest reads."""

    def __init__(
        self,
        reader: SelectionRunReader,
        factory: ResearchCaseFactory,
    ) -> None:
        self._reader = reader
        self._factory = factory

    def create(self, request: CreateResearchCaseRequest) -> ResearchCaseView:
        """Build the stable case or fail closed on unusable/foreign candidates."""
        if not request.selection_run_id.strip():
            raise _error(
                "selection run identity is required",
                reason="invalid_selection_run_id",
            )
        run = self._reader.get(request.selection_run_id)
        if run is None:
            raise _error(
                "selection run not found",
                reason="selection_run_not_found",
                selection_run_id=request.selection_run_id,
            )
        if run.status is SelectionRunStatus.BLOCKED or not run.candidates:
            raise _error(
                "blocked SelectionRun cannot create a Research Case",
                reason="selection_run_blocked",
                selection_run_id=run.run_id,
            )
        requested = request.candidate_instrument_ids
        if len(set(requested)) != len(requested):
            raise _error(
                "Research Case candidates must be unique",
                reason="research_case_candidate_invalid",
            )
        requested_ids = set(requested)
        available_ids = {item.instrument_id for item in run.candidates}
        if requested_ids and not requested_ids.issubset(available_ids):
            raise _error(
                "Research Case candidates must come from the exact SelectionRun",
                reason="research_case_candidate_invalid",
                invalid_candidate_ids=tuple(sorted(requested_ids - available_ids)),
            )
        candidate_ids = tuple(
            item.instrument_id
            for item in run.candidates
            if not requested_ids or item.instrument_id in requested_ids
        )
        try:
            return self._factory.create(
                ResearchCaseMaterial(
                    selection_run_id=run.run_id,
                    selection_run_hash=canonical_selection_run_hash(run),
                    selection_input_hash=run.input_hash,
                    selection_spec_hash=run.spec_hash,
                    objective=request.objective,
                    asset_kind=run.asset_kind.value,
                    as_of=run.as_of,
                    knowledge_cutoff=run.knowledge_cutoff,
                    publication_cutoff=run.publication_cutoff,
                    universe_snapshot_id=run.universe_snapshot_id,
                    industry_rotation_snapshot_id=run.industry_rotation_snapshot_id,
                    source_snapshot_ids=run.source_snapshot_ids,
                    candidate_instrument_ids=candidate_ids,
                    selection_status=run.status.value,
                    missing_inputs=run.missing_inputs,
                )
            )
        except ValueError as exc:
            raise _error(
                "Research Case lineage is invalid",
                reason="research_case_lineage_invalid",
            ) from exc
