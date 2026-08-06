"""Append-only review packet store mixin for experiment storage."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ReviewPacket,
)
from ditto_analysis.experiments.models import ExperimentId
from ditto_analysis.experiments.persistence import ArtifactRecord, LeaseFence
from ditto_analysis.research._indexed_artifacts import (
    ArtifactIndexWriter,
    IndexedArtifactIO,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)
from ditto_analysis.storage.sqlite.experiments.reader import SQLiteExperimentReader

__all__ = ["SQLiteExperimentReviewPacketMixin"]


class SQLiteExperimentReviewPacketMixin:
    """Publish and pin content-addressed review packets for durable governance."""

    _database: ResearchExperimentDatabase
    _reader: SQLiteExperimentReader

    def publish_review_packet(
        self,
        packet: ReviewPacket,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        created_at: datetime,
    ) -> ArtifactRecord:
        """Persist and one-way pin a review packet under its immutable identity."""
        if packet.schema_version != REVIEW_PACKET_SCHEMA_VERSION:
            raise ExperimentSpecError(
                "legacy review packet schemas are read-only",
                details={"reason_code": "review_packet_schema_read_only"},
            )
        bundle_hash = packet.bundle_hash
        spec = ArtifactPublicationSpec(
            artifact_id=f"review-packet-{bundle_hash}",
            experiment_id=ExperimentId(packet.lineage.experiment_id),
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            artifact_kind="review_packet",
            relative_path=(
                f"experiments/{packet.lineage.experiment_id}/review-packet.json"
            ),
            reproduction_fingerprint=bundle_hash,
            audit={"created_at": created_at.isoformat()},
            created_at=created_at,
        )
        io = IndexedArtifactIO(
            artifact_root=self._database.artifact_root,
            reader=self._reader,
            writer=cast("ArtifactIndexWriter", self),
        )
        published = io.publish_json(
            spec,
            packet.canonical_payload(),
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )
        if published.is_pinned:
            return published
        return io.pin(
            published.artifact_id,
            expected_revision=published.revision,
            pinned_at=created_at,
        )
