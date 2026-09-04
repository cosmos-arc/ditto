"""PIT-bound evidence adapters for persisted industry and selection artifacts."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from ditto_strategy.industry_rotation.contracts import IndustryRotationSnapshot
from ditto_strategy.industry_rotation.store import IndustryRotationReader
from ditto_strategy.selection.contracts import SelectionRun
from ditto_strategy.selection.store import SelectionRunReader

from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    IndustryRotationEvidenceReadModel,
    SelectionRunEvidenceReadModel,
)
from ditto_application.queries.selection_views import (
    to_industry_rotation_view,
    to_selection_run_view,
)

__all__ = ["IndustryRotationEvidenceQueryFacade", "SelectionRunEvidenceQueryFacade"]

_SHA256_HEX_LENGTH = 64


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"selection evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _content_hash(identity: str, *, kind: str) -> str:
    digest = identity.rpartition(":")[2]
    if len(digest) != _SHA256_HEX_LENGTH or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise _error(
            "SELECTION_EVIDENCE_IDENTITY_INVALID",
            "artifact_identity_has_no_sha256",
            artifact_kind=kind,
            artifact_id=identity,
        )
    return digest


def _artifact_context(
    *,
    as_of: datetime,
    knowledge_cutoff: datetime,
    publication_cutoff: datetime,
    source_snapshot_ids: tuple[str, ...],
) -> EvidenceTemporalContext:
    snapshot_set_id = aggregate_source_snapshot_ids(source_snapshot_ids)
    if snapshot_set_id is None:
        raise _error(
            "SELECTION_EVIDENCE_SNAPSHOT_REQUIRED",
            "source_snapshot_set_empty",
        )
    return EvidenceTemporalContext(
        decision_time=as_of,
        knowledge_cutoff=knowledge_cutoff,
        publication_cutoff=publication_cutoff,
        source_snapshot_id=snapshot_set_id,
    )


def _verify_context(
    *,
    artifact_context: EvidenceTemporalContext,
    requested_context: EvidenceTemporalContext,
    artifact_id: str,
) -> None:
    if artifact_context != requested_context:
        raise _error(
            "SELECTION_EVIDENCE_CONTEXT_MISMATCH",
            "artifact_context_does_not_match_host_context",
            artifact_id=artifact_id,
        )


def _rotation_context(value: IndustryRotationSnapshot) -> EvidenceTemporalContext:
    return _artifact_context(
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        source_snapshot_ids=value.source_snapshot_ids,
    )


def _selection_context(value: SelectionRun) -> EvidenceTemporalContext:
    return _artifact_context(
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        source_snapshot_ids=value.source_snapshot_ids,
    )


class IndustryRotationEvidenceQueryFacade:
    """Authenticate one exact saved ranking for governed Agent use."""

    def __init__(self, reader: IndustryRotationReader) -> None:
        self._reader = reader

    def get_evidence(
        self,
        *,
        snapshot_id: str,
        context: EvidenceTemporalContext,
    ) -> IndustryRotationEvidenceReadModel:
        """Return complete ranked factors only under the exact host context."""
        value = self._reader.get_rotation(snapshot_id)
        if value is None:
            raise _error(
                "INDUSTRY_ROTATION_EVIDENCE_NOT_FOUND",
                "industry_rotation_snapshot_not_found",
                snapshot_id=snapshot_id,
            )
        artifact_context = _rotation_context(value)
        _verify_context(
            artifact_context=artifact_context,
            requested_context=context,
            artifact_id=value.snapshot_id,
        )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value=asdict(to_industry_rotation_view(value)),
        )
        return IndustryRotationEvidenceReadModel(
            snapshot_id=value.snapshot_id,
            status=value.status.value,
            temporal_context=artifact_context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=value.snapshot_id,
                    artifact_kind="industry_rotation_snapshot",
                    content_hash=_content_hash(
                        value.snapshot_id, kind="industry_rotation"
                    ),
                ),
            ),
            lineage=tuple(
                dict.fromkeys(
                    (
                        value.snapshot_id,
                        *(f"snapshot:{item}" for item in value.source_snapshot_ids),
                        *(
                            (value.market_context_feature_set_id,)
                            if value.market_context_feature_set_id is not None
                            else ()
                        ),
                    )
                )
            ),
        )


class SelectionRunEvidenceQueryFacade:
    """Authenticate one saved run without changing candidates or exclusions."""

    def __init__(self, reader: SelectionRunReader) -> None:
        self._reader = reader

    def get_evidence(
        self,
        *,
        run_id: str,
        context: EvidenceTemporalContext,
    ) -> SelectionRunEvidenceReadModel:
        """Return exact rank, factor, why-in and why-out evidence."""
        value = self._reader.get(run_id)
        if value is None:
            raise _error(
                "SELECTION_RUN_EVIDENCE_NOT_FOUND",
                "selection_run_not_found",
                run_id=run_id,
            )
        artifact_context = _selection_context(value)
        _verify_context(
            artifact_context=artifact_context,
            requested_context=context,
            artifact_id=value.run_id,
        )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value=asdict(to_selection_run_view(value)),
        )
        return SelectionRunEvidenceReadModel(
            run_id=value.run_id,
            status=value.status.value,
            temporal_context=artifact_context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=value.run_id,
                    artifact_kind="selection_run",
                    content_hash=_content_hash(value.run_id, kind="selection_run"),
                ),
            ),
            lineage=tuple(
                dict.fromkeys(
                    (
                        value.run_id,
                        value.universe_snapshot_id,
                        *(
                            (value.industry_rotation_snapshot_id,)
                            if value.industry_rotation_snapshot_id is not None
                            else ()
                        ),
                        *(f"snapshot:{item}" for item in value.source_snapshot_ids),
                    )
                )
            ),
        )
