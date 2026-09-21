"""Read saved research dataset identities and reports without writes."""

from __future__ import annotations

from dataclasses import asdict

from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.specs import DatasetSnapshot, KnownAtPolicy
from ditto_features.errors import DerivedNotFoundError


class ResearchDatasetQuery:
    """Only completed catalog snapshots are visible to readers."""

    def __init__(
        self,
        *,
        research_catalog_service: ResearchCatalogService,
        research_artifact_service: ResearchArtifactService,
    ) -> None:
        self._catalog = research_catalog_service
        self._artifacts = research_artifact_service

    def get_snapshot(self, snapshot_id: str) -> DatasetSnapshot:
        """Read one exact completed snapshot; never rebuild or choose latest."""
        record = self._catalog.get_dataset_snapshot(snapshot_id)
        if record is None:
            raise DerivedNotFoundError(derived_id=snapshot_id)
        fields = asdict(record)
        fields["start"] = fields.pop("snapshot_start")
        fields["end"] = fields.pop("snapshot_end")
        fields["known_at_policy"] = KnownAtPolicy(record.known_at_policy)
        return DatasetSnapshot(**fields)

    def load_build_report(self, snapshot: DatasetSnapshot) -> dict[str, object]:
        """Load the report via its catalog-owned path."""
        saved = self.get_snapshot(snapshot.snapshot_id)
        return self._artifacts.read_json(
            f"{saved.data_path.rsplit('/', 1)[0]}/build_report.json"
        )
