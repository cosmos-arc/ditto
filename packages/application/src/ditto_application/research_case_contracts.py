"""Application-owned handoff contract for SelectionRun research cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_kernel.identity import InstrumentId

__all__ = [
    "ResearchCaseFactory",
    "ResearchCaseMaterial",
    "ResearchCaseView",
]


@dataclass(frozen=True, slots=True)
class ResearchCaseMaterial:
    """Complete immutable material passed to the isolated analysis plane."""

    selection_run_id: str
    selection_run_hash: str
    selection_input_hash: str
    selection_spec_hash: str
    objective: str
    asset_kind: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    universe_snapshot_id: str
    industry_rotation_snapshot_id: str | None
    source_snapshot_ids: tuple[str, ...]
    candidate_instrument_ids: tuple[InstrumentId, ...]
    selection_status: str
    missing_inputs: tuple[str, ...]


class ResearchCaseView(Protocol):
    """Narrow structural result returned by an analysis-plane factory."""

    @property
    def case_id(self) -> str:
        """Return the immutable research-case identity."""
        ...

    @property
    def content_hash(self) -> str:
        """Return the canonical case content hash."""
        ...

    @property
    def schema_version(self) -> int:
        """Return the case schema version."""
        ...

    @property
    def selection_run_id(self) -> str:
        """Return the originating Selection run identity."""
        ...

    @property
    def selection_run_hash(self) -> str:
        """Return the originating Selection run hash."""
        ...

    @property
    def selection_input_hash(self) -> str:
        """Return the exact Selection input hash."""
        ...

    @property
    def selection_spec_hash(self) -> str:
        """Return the exact Selection specification hash."""
        ...

    @property
    def objective(self) -> str:
        """Return the bounded research objective."""
        ...

    @property
    def asset_kind(self) -> str:
        """Return the selected asset kind."""
        ...

    @property
    def as_of(self) -> datetime:
        """Return the decision time."""
        ...

    @property
    def knowledge_cutoff(self) -> datetime:
        """Return the fail-closed knowledge cutoff."""
        ...

    @property
    def publication_cutoff(self) -> datetime:
        """Return the fail-closed publication cutoff."""
        ...

    @property
    def universe_snapshot_id(self) -> str:
        """Return the frozen universe snapshot identity."""
        ...

    @property
    def industry_rotation_snapshot_id(self) -> str | None:
        """Return the optional industry-rotation snapshot identity."""
        ...

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]:
        """Return all frozen source snapshot identities."""
        ...

    @property
    def candidate_instrument_ids(self) -> tuple[InstrumentId, ...]:
        """Return the selected candidate instruments."""
        ...

    @property
    def selection_status(self) -> str:
        """Return the originating Selection status."""
        ...

    @property
    def missing_inputs(self) -> tuple[str, ...]:
        """Return explicit missing Selection inputs."""
        ...


class ResearchCaseFactory(Protocol):
    """Port implemented only at the apps composition boundary."""

    def create(self, material: ResearchCaseMaterial) -> ResearchCaseView:
        """Validate and create one immutable analysis-owned case."""
        ...
