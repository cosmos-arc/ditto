"""Production fail-closed validation authority for R3 experiment planning."""

from __future__ import annotations

from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityRequest,
    ResearchValidationAuthorityResult,
)

__all__ = ["ProductionResearchValidationAuthorityProbe"]


class ProductionResearchValidationAuthorityProbe:
    """Refuse authority until runtime semantics and PIT membership are registered."""

    def probe(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> ResearchValidationAuthorityResult:
        """Inspect only proven runtime facts; never echo caller assertions."""
        runtime = request.runtime_validation
        if runtime is None:
            return ResearchValidationAuthorityResult(
                False,
                "RUNTIME_VALIDATION_EVIDENCE_MISSING",
                "runtime_validation_evidence_missing",
                "build every candidate runtime before requesting validation authority",
                None,
            )
        if not runtime.has_registered_isolation:
            return ResearchValidationAuthorityResult(
                False,
                "VALIDATION_SEMANTICS_UNREGISTERED",
                "runtime_validation_semantics_unregistered",
                "register typed forward, holding, and execution-lag semantics",
                None,
            )
        return ResearchValidationAuthorityResult(
            False,
            "PIT_UNIVERSE_UNRESOLVED",
            "authoritative_pit_universe_evidence_unavailable",
            "register a PIT universe membership authority before launch",
            None,
        )
