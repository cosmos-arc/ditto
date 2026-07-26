"""Indexed frozen research inputs resolver backed by ``ResearchArtifactService``."""

from __future__ import annotations

from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.processes.experiments._execution_bundle_inputs import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    FrozenResearchExecutionInputs,
    FrozenResearchInputRequest,
    research_execution_error,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)

__all__ = ["IndexedResearchInputsResolver"]

_RULES_ARTIFACT_KIND = "instrument_rules"


class IndexedResearchInputsResolver:
    """
    Production ``FrozenResearchInputsResolver`` backed by indexed artifacts.

    The resolver reads the canonical snapshot manifest and the frozen
    instrument-rules artifact by their content-addressed identities and
    rebuilds the same ``FrozenResearchExecutionInputs`` trust boundary used
    during planning. The manifest artifact is keyed by ``snapshot_id``; every
    content-addressed input is keyed by its ``input_id``.
    """

    def __init__(self, *, artifact_service: ResearchArtifactService) -> None:
        self._artifacts = artifact_service

    def resolve(
        self,
        request: FrozenResearchInputRequest,
    ) -> FrozenResearchExecutionInputs:
        """Return verified snapshot and instrument-rules bindings for one request."""
        manifest_bytes = self._artifacts.read_indexed_artifact_bytes(
            request.snapshot.snapshot_id,
        )
        snapshot_manifest = VerifiedResearchSnapshotManifest(
            exact_snapshot=request.snapshot,
            manifest_bytes=manifest_bytes,
        )
        rules_evidence = _select_single_rules_evidence(snapshot_manifest)
        rules_bytes = self._artifacts.read_indexed_artifact_bytes(
            rules_evidence.input_id,
        )
        instrument_rules = VerifiedInstrumentRulesArtifact(
            input_evidence=rules_evidence,
            artifact_bytes=rules_bytes,
        )
        return FrozenResearchExecutionInputs(
            snapshot_manifest=snapshot_manifest,
            universe=request.universe,
            membership_projection_hash=request.membership_projection_hash,
            instrument_rules=instrument_rules,
        )


def _select_single_rules_evidence(
    snapshot_manifest: VerifiedResearchSnapshotManifest,
) -> ContentAddressedResearchInput:
    binding = snapshot_manifest.snapshot_binding
    matches = tuple(
        item for item in binding.inputs if item.artifact_kind == _RULES_ARTIFACT_KIND
    )
    if len(matches) != 1:
        raise research_execution_error(
            "instrument_rules_evidence_missing_or_ambiguous",
            observed_count=len(matches),
        )
    return matches[0]
