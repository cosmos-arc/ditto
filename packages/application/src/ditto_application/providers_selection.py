"""Selection workspace DI provider."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.industry_rotation.store import (
    IndustryRotationReader,
    IndustryRotationWriter,
)
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.selection.store import SelectionRunReader, SelectionRunWriter

from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
)
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_evidence import (
    IndustryRotationEvidenceQueryFacade,
    SelectionRunEvidenceQueryFacade,
)
from ditto_application.queries.selection_runs import SelectionRunQueryService
from ditto_application.research_case_contracts import ResearchCaseFactory

__all__ = ["AppSelectionProvider"]


class AppSelectionProvider(Provider):
    """Compose the selection capability behind application-owned contracts."""

    scope = Scope.APP

    @provide
    def run_industry_and_security_selection(
        self,
        rotation_service: IndustryRotationService,
        selection_pipeline: SelectionPipeline,
        rotation_writer: IndustryRotationWriter,
        run_writer: SelectionRunWriter,
    ) -> RunIndustryAndSecuritySelection:
        """Bind the cross-plane selection process to strategy ports."""
        return RunIndustryAndSecuritySelection(
            rotation_service=rotation_service,
            selection_pipeline=selection_pipeline,
            rotation_writer=rotation_writer,
            run_writer=run_writer,
        )

    @provide
    def selection_workspace_facade(
        self,
        process: RunIndustryAndSecuritySelection,
    ) -> SelectionWorkspaceFacade:
        """Expose typed create-selection requests to transport adapters."""
        return SelectionWorkspaceFacade(process)

    @provide
    def create_research_case_from_selection(
        self,
        reader: SelectionRunReader,
        factory: ResearchCaseFactory,
    ) -> CreateResearchCaseFromSelection:
        """Bind Analysis Research Cases to exact persisted SelectionRuns."""
        return CreateResearchCaseFromSelection(reader, factory)

    @provide
    def selection_run_query_service(
        self,
        reader: SelectionRunReader,
    ) -> SelectionRunQueryService:
        """Expose exact saved SelectionRun reads and comparisons."""
        return SelectionRunQueryService(reader)

    @provide
    def industry_rotation_query_service(
        self,
        reader: IndustryRotationReader,
    ) -> IndustryRotationQueryService:
        """Expose exact persisted rotation snapshots to UI transports."""
        return IndustryRotationQueryService(reader)

    @provide
    def industry_rotation_evidence_query(
        self,
        reader: IndustryRotationReader,
    ) -> IndustryRotationEvidenceQueryFacade:
        """Bind exact persisted rankings to the Agent-facing application port."""
        return IndustryRotationEvidenceQueryFacade(reader)

    @provide
    def selection_run_evidence_query(
        self,
        reader: SelectionRunReader,
    ) -> SelectionRunEvidenceQueryFacade:
        """Bind exact saved runs to the Agent-facing application port."""
        return SelectionRunEvidenceQueryFacade(reader)
