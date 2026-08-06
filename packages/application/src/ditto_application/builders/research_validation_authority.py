"""Production fail-closed validation authority for R3 experiment planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_application.research_certification_contracts import (
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    ResearchValidationAuthorityRequest,
    ResearchValidationAuthorityResult,
)
from ditto_application.research_validation_protocol import ValidationProtocolRequest

__all__ = [
    "ProductionResearchValidationAuthorityProbe",
    "SnapshotValidationAuthorityFacts",
    "SnapshotValidationAuthoritySource",
]


@dataclass(frozen=True, slots=True)
class SnapshotValidationAuthorityFacts:
    """Authority-owned protocol and bindings derived from immutable snapshot bytes."""

    protocol: ValidationProtocolRequest
    universe_membership_hash: str
    dataset_bindings: tuple[ResearchDatasetRequirement, ...]


class SnapshotValidationAuthoritySource(Protocol):
    """Resolve immutable validation facts without trusting request declarations."""

    def resolve(
        self,
        request: ResearchValidationAuthorityRequest,
    ) -> SnapshotValidationAuthorityFacts:
        """Return facts measured from the exact research snapshot."""
        ...


class ProductionResearchValidationAuthorityProbe:
    """Sign only runtime facts cross-bound to an immutable snapshot authority."""

    def __init__(
        self,
        source: SnapshotValidationAuthoritySource | None = None,
    ) -> None:
        self._source = source

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
        if self._source is None:
            return _pit_universe_unresolved()
        try:
            facts = self._source.resolve(request)
            if type(facts) is not SnapshotValidationAuthorityFacts:
                return _invalid_snapshot_authority()
            evidence = ResearchValidationAuthorityEvidence.create(
                protocol=facts.protocol,
                snapshot_identity=request.snapshot_identity,
                runtime_evidence_hash=runtime.payload_hash,
                universe_membership_hash=facts.universe_membership_hash,
                requires_pit_universe=runtime.requires_pit_universe,
                dataset_bindings=facts.dataset_bindings,
            )
        except Exception:
            return _invalid_snapshot_authority()
        return ResearchValidationAuthorityResult(True, None, None, None, evidence)


def _pit_universe_unresolved() -> ResearchValidationAuthorityResult:
    return ResearchValidationAuthorityResult(
        False,
        "PIT_UNIVERSE_UNRESOLVED",
        "authoritative_pit_universe_evidence_unavailable",
        "register a PIT universe membership authority before launch",
        None,
    )


def _invalid_snapshot_authority() -> ResearchValidationAuthorityResult:
    return ResearchValidationAuthorityResult(
        False,
        "VALIDATION_AUTHORITY_INVALID",
        "snapshot_validation_authority_invalid",
        "rebuild the exact snapshot validation evidence",
        None,
    )
