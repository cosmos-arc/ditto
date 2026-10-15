"""
Lease-fenced indexed publication of model-candidate artifacts (#268).

Bridges the frozen ``ModelTrainingRecord``/``ModelPredictionRecord`` contracts
into the existing indexed experiment-artifact namespace, so published model
evidence is immutable, content-verified, and listed by the existing experiment
artifact read surface. Publication happens fold-scoped under the caller's
scheduler lease; nothing here can mark a trial successful by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

import orjson
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.model_lineage import (
    ModelPredictionRecord,
    ModelTrainingRecord,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    canonical_payload,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "IndexedModelArtifactSink",
    "ModelArtifactPublicationContext",
    "ResearchArtifactServicePort",
]

_ARTIFACT_KIND_TRAINING = "model_training_state"
_ARTIFACT_KIND_PREDICTIONS = "model_predictions"


def _publication_error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "model artifact publication failed closed",
        details={"code": "MODEL_ARTIFACT_PUBLISH_FAILED", "reason": reason, **details},
    )


class ResearchArtifactServicePort(Protocol):
    """Indexed publication port implemented by ResearchArtifactService."""

    def publish_indexed_json(
        self,
        spec: ArtifactPublicationSpec,
        data: dict[str, object],
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish one immutable JSON artifact into the indexed namespace."""
        ...


@dataclass(frozen=True, slots=True)
class ModelArtifactPublicationContext:
    """Experiment lineage and write authority for one publication batch."""

    experiment_id: ExperimentId
    candidate_id: CandidateId
    fold_id: FoldId | None
    attempt_id: AttemptId | None
    reproduction_fingerprint: ContentHash
    lease_fence: LeaseFence
    now_epoch_us: int

    def __post_init__(self) -> None:
        """Validate typed lineage and lease authority shape."""
        if (
            type(self.experiment_id) is not ExperimentId
            or type(self.candidate_id) is not CandidateId
            or type(self.reproduction_fingerprint) is not ContentHash
        ):
            raise _publication_error("publication_identity_invalid")
        if self.fold_id is not None and type(self.fold_id) is not FoldId:
            raise _publication_error("publication_identity_invalid")
        if self.attempt_id is not None and type(self.attempt_id) is not AttemptId:
            raise _publication_error("publication_identity_invalid")
        if self.fold_id is None and self.attempt_id is not None:
            raise _publication_error("publication_lineage_gap")
        if type(self.lease_fence) is not LeaseFence:
            raise _publication_error("publication_lease_invalid")
        if type(self.now_epoch_us) is not int or self.now_epoch_us < 0:
            raise _publication_error("publication_clock_invalid")


class IndexedModelArtifactSink:
    """Publish model evidence through the existing indexed artifact store."""

    def __init__(self, artifact_service: ResearchArtifactServicePort) -> None:
        self._service = artifact_service

    def _spec(
        self,
        context: ModelArtifactPublicationContext,
        filename: str,
        artifact_suffix: str,
        artifact_kind: str,
        created_at: datetime,
    ) -> ArtifactPublicationSpec:
        parts = [
            "experiments",
            str(context.experiment_id),
            "candidates",
            str(context.candidate_id),
        ]
        if context.fold_id is not None:
            parts.extend(("folds", str(context.fold_id)))
        if context.attempt_id is not None:
            parts.extend(("attempts", str(context.attempt_id)))
        relative_path = "/".join([*parts, filename])
        audit: dict[str, object] = {
            "created_at": created_at.isoformat(),
            "artifact_family": "model_candidate",
        }
        if context.attempt_id is not None:
            audit["run_id"] = f"model-{context.attempt_id}"
            audit["attempt_id"] = str(context.attempt_id)
        return ArtifactPublicationSpec(
            artifact_id=f"model-{artifact_suffix}",
            experiment_id=context.experiment_id,
            candidate_id=context.candidate_id,
            fold_id=context.fold_id,
            attempt_id=context.attempt_id,
            artifact_kind=artifact_kind,
            relative_path=relative_path,
            reproduction_fingerprint=context.reproduction_fingerprint,
            audit=audit,
            created_at=created_at,
        )

    def publish_training(
        self,
        context: ModelArtifactPublicationContext,
        training: ModelTrainingRecord,
        model_state_bytes: bytes,
        transform_state_bytes: bytes,
    ) -> tuple[ArtifactRecord, ArtifactRecord, ArtifactRecord]:
        """Publish record, model state, and transform state immutably."""
        # Replays of the same publication batch must carry the same timestamp,
        # so the immutable-replay contract stays byte-stable.
        created_at = datetime.fromtimestamp(context.now_epoch_us / 1_000_000, tz=UTC)
        record_payload = dict(training.canonical_payload())
        record_spec = self._spec(
            context,
            "model-training.json",
            f"training-{training.artifact_hash}",
            _ARTIFACT_KIND_TRAINING,
            created_at,
        )
        model_spec = self._spec(
            context,
            "model-state.json",
            f"model-state-{training.model_state_sha256}",
            _ARTIFACT_KIND_TRAINING,
            created_at,
        )
        transform_spec = self._spec(
            context,
            "transform-state.json",
            f"transform-state-{training.transform_state_sha256}",
            _ARTIFACT_KIND_TRAINING,
            created_at,
        )
        decoded_model: object = orjson.loads(model_state_bytes)
        decoded_transform: object = orjson.loads(transform_state_bytes)
        if not isinstance(decoded_model, dict) or not isinstance(
            decoded_transform, dict
        ):
            raise _publication_error("state_bytes_not_json_object")
        model_state = cast("dict[str, object]", decoded_model)
        transform_state = cast("dict[str, object]", decoded_transform)
        record = self._service.publish_indexed_json(
            record_spec,
            record_payload,
            lease_fence=context.lease_fence,
            now_epoch_us=context.now_epoch_us,
        )
        model = self._service.publish_indexed_json(
            model_spec,
            dict(model_state),
            lease_fence=context.lease_fence,
            now_epoch_us=context.now_epoch_us,
        )
        transform = self._service.publish_indexed_json(
            transform_spec,
            dict(transform_state),
            lease_fence=context.lease_fence,
            now_epoch_us=context.now_epoch_us,
        )
        self._verify_published_bytes(record, training.canonical_payload())
        return record, model, transform

    def publish_predictions(
        self,
        context: ModelArtifactPublicationContext,
        predictions: ModelPredictionRecord,
    ) -> ArtifactRecord:
        """Publish one prediction artifact bound to its training artifact."""
        created_at = datetime.fromtimestamp(context.now_epoch_us / 1_000_000, tz=UTC)
        spec = self._spec(
            context,
            "model-predictions.json",
            f"predictions-{predictions.artifact_hash}",
            _ARTIFACT_KIND_PREDICTIONS,
            created_at,
        )
        payload = dict(predictions.canonical_payload())
        record = self._service.publish_indexed_json(
            spec,
            payload,
            lease_fence=context.lease_fence,
            now_epoch_us=context.now_epoch_us,
        )
        self._verify_published_bytes(record, payload)
        return record

    @staticmethod
    def _verify_published_bytes(
        record: ArtifactRecord,
        payload: dict[str, object],
    ) -> None:
        expected = canonical_payload(payload).content_hash
        if record.content_hash != expected:
            raise _publication_error(
                "published_content_hash_drift",
                artifact_id=record.artifact_id,
            )
