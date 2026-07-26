"""Indexed research artifact loader backed by ``ResearchArtifactService``."""

from __future__ import annotations

from io import BytesIO

import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService

from ditto_application.processes.experiments._execution_bundle_inputs import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)

__all__ = ["IndexedResearchArtifactLoader"]


class IndexedResearchArtifactLoader:
    """
    Production ``ExactResearchArtifactLoader`` backed by indexed artifacts.

    The loader reads raw verified bytes from the indexed artifact namespace
    and rebuilds the same trust boundaries used during planning. It never
    performs catalog lookup, provider fallback, or unverified path reads.
    """

    def __init__(self, *, artifact_service: ResearchArtifactService) -> None:
        self._artifacts = artifact_service

    def load_frame(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedResearchFrame:
        """Load and verify one Parquet frame addressed by ``evidence.input_id``."""
        artifact_bytes = self._artifacts.read_indexed_artifact_bytes(evidence.input_id)
        # VerifiedResearchFrame does not infer source_snapshot_ids from the
        # parsed frame; derive them here so the trust boundary stays caller-free.
        frame = pl.read_parquet(BytesIO(artifact_bytes))
        source_snapshot_ids = tuple(
            frame["source_snapshot_id"].unique().sort().to_list()
        )
        return VerifiedResearchFrame(
            input_evidence=evidence,
            source_snapshot_ids=source_snapshot_ids,
            artifact_bytes=artifact_bytes,
        )

    def load_instrument_rules(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedInstrumentRulesArtifact:
        """Load and verify one instrument-rules Parquet artifact."""
        artifact_bytes = self._artifacts.read_indexed_artifact_bytes(evidence.input_id)
        return VerifiedInstrumentRulesArtifact(
            input_evidence=evidence,
            artifact_bytes=artifact_bytes,
        )
