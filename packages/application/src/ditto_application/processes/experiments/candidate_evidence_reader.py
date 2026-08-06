"""Immutable candidate trace bundles and typed opaque-cursor drill-down reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn, Protocol, cast

from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    FactorContributionEvidence,
    SelectionEvidence,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.processes.experiments._evidence_inputs import (
    project_snapshot_manifest,
    read_unique_preflight_detail,
)
from ditto_application.processes.experiments._fold_selection_trace_artifacts import (
    FoldSelectionTraceArtifactKind,
    LoadedFoldSelectionTraceArtifacts,
)
from ditto_application.processes.experiments._walk_forward_evidence_collection import (
    CollectedWalkForwardEvidence,
    WalkForwardEvidenceAssembler,
)
from ditto_application.processes.experiments.candidate_evidence_cursor import (
    CandidateEvidenceCursor,
    CandidateEvidenceResourceKind,
    decode_candidate_evidence_cursor,
    encode_candidate_evidence_cursor,
)
from ditto_application.processes.experiments.comparison import FoldOutcome
from ditto_application.processes.experiments.scheduler_store import (
    CandidateId,
    ExperimentId,
    ExperimentSchedulerStoreProtocol,
    ExperimentStage,
)

__all__ = [
    "CANDIDATE_EVIDENCE_ARTIFACT_KIND",
    "CANDIDATE_EVIDENCE_SCHEMA_ID",
    "CANDIDATE_EVIDENCE_SCHEMA_VERSION",
    "CandidateEvidenceBundle",
    "CandidateEvidenceCursor",
    "CandidateEvidencePage",
    "CandidateEvidenceReader",
    "CandidateEvidenceResourceKind",
    "build_candidate_evidence_bundle",
    "candidate_evidence_bundle_relative_path",
    "decode_candidate_evidence_cursor",
    "encode_candidate_evidence_cursor",
]

CANDIDATE_EVIDENCE_ARTIFACT_KIND = "candidate_evidence_bundle_v1"
CANDIDATE_EVIDENCE_SCHEMA_ID = "ditto.r3.candidate-evidence-bundle"
CANDIDATE_EVIDENCE_SCHEMA_VERSION = 1
_MAX_PAGE_LIMIT = 100
_ARTIFACT_PREFIX = "candidate-evidence-bundle-v1"


def _error(code: str, reason: str, message: str, **details: object) -> NoReturn:
    raise AppProcessError(
        message,
        details={"code": code, "reason": reason, **details},
    )


def _typed_kind(value: object) -> CandidateEvidenceResourceKind:
    if type(value) is not CandidateEvidenceResourceKind:
        _error(
            "INVALID_CANDIDATE_EVIDENCE_CURSOR",
            "candidate_evidence_cursor_kind_invalid",
            "candidate evidence cursor is invalid",
        )
    return value


type CandidateEvidenceItem = Mapping[str, object]


class _ArtifactRecord(Protocol):
    @property
    def artifact_id(self) -> str: ...

    @property
    def artifact_kind(self) -> str: ...

    @property
    def candidate_id(self) -> object: ...

    @property
    def content_hash(self) -> object: ...

    @property
    def manifest(self) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class CandidateEvidenceBundle:
    """Canonical immutable bundle over comparison-selected fold attempts."""

    manifest: Mapping[str, object]
    fold_sources: tuple[Mapping[str, object], ...]
    selections: tuple[CandidateEvidenceItem, ...]
    exclusions: tuple[CandidateEvidenceItem, ...]
    factor_contributions: tuple[CandidateEvidenceItem, ...]

    @property
    def payload(self) -> dict[str, object]:
        """Return the exact generic JSON artifact payload."""
        return {
            "fold_sources": [dict(item) for item in self.fold_sources],
            "manifest": dict(self.manifest),
            "resources": {
                "exclusions": [dict(item) for item in self.exclusions],
                "factor_contributions": [
                    dict(item) for item in self.factor_contributions
                ],
                "selections": [dict(item) for item in self.selections],
            },
            "schema_id": CANDIDATE_EVIDENCE_SCHEMA_ID,
            "schema_version": CANDIDATE_EVIDENCE_SCHEMA_VERSION,
        }

    @property
    def content_hash(self) -> str:
        """Hash the full manifest, fold refs, and typed resources."""
        return canonical_request_hash(self.payload)

    @property
    def artifact_id(self) -> str:
        """Return the content-addressed generic artifact identity."""
        return f"{_ARTIFACT_PREFIX}-{self.content_hash}"

    def items(
        self,
        kind: CandidateEvidenceResourceKind,
    ) -> tuple[CandidateEvidenceItem, ...]:
        """Return one canonical resource without stringly typed dispatch."""
        return {
            CandidateEvidenceResourceKind.SELECTIONS: self.selections,
            CandidateEvidenceResourceKind.EXCLUSIONS: self.exclusions,
            CandidateEvidenceResourceKind.FACTOR_CONTRIBUTIONS: (
                self.factor_contributions
            ),
        }[_typed_kind(kind)]


def _record_ref(record: _ArtifactRecord) -> dict[str, object]:
    audit = record.manifest.get("audit")
    if not isinstance(audit, Mapping):
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_source_schema_invalid",
            "candidate evidence source schema is invalid",
            artifact_id=record.artifact_id,
        )
    typed_audit = cast("Mapping[str, object]", audit)
    if type(typed_audit.get("schema_version")) is not int:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_source_schema_invalid",
            "candidate evidence source schema is invalid",
            artifact_id=record.artifact_id,
        )
    return {
        "artifact_id": record.artifact_id,
        "artifact_kind": record.artifact_kind,
        "content_hash": str(record.content_hash),
        "schema_version": typed_audit["schema_version"],
    }


def _current_comparison_revision(events: Sequence[object]) -> int:
    """Resolve the one durable candidate-selection stage revision."""
    matches = tuple(
        event
        for event in events
        if getattr(event, "reason_code", None) == "scheduler_stage_complete"
        and getattr(event, "stage", None) is ExperimentStage.CANDIDATE_SELECTION
    )
    if len(matches) != 1:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_comparison_revision_not_unique",
            "candidate evidence comparison revision is invalid",
        )
    revision = getattr(matches[0], "subject_revision", None)
    if type(revision) is not int or revision <= 0:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_comparison_revision_invalid",
            "candidate evidence comparison revision is invalid",
        )
    return revision


def _evidence_hash(
    *,
    record: _ArtifactRecord,
    item: Mapping[str, object],
) -> str:
    return str(
        canonical_request_hash(
            {
                "item": dict(item),
                "source_artifact_id": record.artifact_id,
                "source_content_hash": str(record.content_hash),
            }
        )
    )


def _item_base(
    *,
    fold_ordinal: int,
    fold_id: str,
    trade_date: str,
    instrument_id: object,
) -> dict[str, object]:
    return {
        "fold_id": fold_id,
        "instrument_id": instrument_id,
        "trade_date": trade_date,
        "validation_fold_ordinal": fold_ordinal,
    }


def _selection_item(
    event: SelectionEvidence,
    *,
    fold_ordinal: int,
    fold_id: str,
    record: _ArtifactRecord,
) -> dict[str, object]:
    item = {
        **_item_base(
            fold_ordinal=fold_ordinal,
            fold_id=fold_id,
            trade_date=event.trade_date,
            instrument_id=event.instrument_id,
        ),
        "rank": event.rank,
        "score": event.score,
        "selected": event.selected,
    }
    return {**item, "evidence_hash": _evidence_hash(record=record, item=item)}


def _exclusion_item(
    event: ExclusionEvidence,
    *,
    fold_ordinal: int,
    fold_id: str,
    record: _ArtifactRecord,
) -> dict[str, object]:
    item = {
        **_item_base(
            fold_ordinal=fold_ordinal,
            fold_id=fold_id,
            trade_date=event.trade_date,
            instrument_id=event.instrument_id,
        ),
        "message": event.message,
        "reason_code": event.reason_code.value,
        "stage": event.stage,
    }
    return {**item, "evidence_hash": _evidence_hash(record=record, item=item)}


def _contribution_item(
    event: FactorContributionEvidence,
    *,
    fold_ordinal: int,
    fold_id: str,
    record: _ArtifactRecord,
) -> dict[str, object]:
    item = {
        **_item_base(
            fold_ordinal=fold_ordinal,
            fold_id=fold_id,
            trade_date=event.trade_date,
            instrument_id=event.instrument_id,
        ),
        "contribution": event.contribution,
        "factor_id": event.factor_name,
        "rank": event.rank,
        "selected": event.selected,
    }
    return {**item, "evidence_hash": _evidence_hash(record=record, item=item)}


def _trace_by_candidate(
    collected: CollectedWalkForwardEvidence,
    candidate_id: CandidateId,
) -> dict[tuple[object, object], LoadedFoldSelectionTraceArtifacts]:
    return {
        (trace.identity.fold_id, trace.identity.attempt_id): trace
        for trace in collected.selection_traces
        if trace.identity.candidate_id == candidate_id
    }


def build_candidate_evidence_bundle(
    collected: CollectedWalkForwardEvidence,
    *,
    candidate_id: str,
    comparison_revision: int,
) -> CandidateEvidenceBundle:
    """Freeze exact terminal comparison lineage into one candidate JSON bundle."""
    if type(collected) is not CollectedWalkForwardEvidence:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_collection_invalid",
            "candidate evidence collection is invalid",
        )
    if type(comparison_revision) is not int or comparison_revision < 0:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_revision_invalid",
            "candidate evidence revision is invalid",
        )
    typed_candidate_id = CandidateId(candidate_id)
    rows = tuple(
        row
        for row in collected.source_rows
        if row.candidate_id == typed_candidate_id
        and row.outcome is FoldOutcome.COMPLETED
    )
    if not rows:
        _error(
            "CANDIDATE_EVIDENCE_NOT_FOUND",
            "candidate_evidence_candidate_not_found",
            "candidate evidence was not found",
            candidate_id=candidate_id,
        )
    traces = _trace_by_candidate(collected, typed_candidate_id)
    fold_sources: list[Mapping[str, object]] = []
    selections: list[CandidateEvidenceItem] = []
    exclusions: list[CandidateEvidenceItem] = []
    contributions: list[CandidateEvidenceItem] = []
    for row in sorted(rows, key=lambda item: (item.fold_ordinal, str(item.fold_id))):
        trace = traces.get((row.fold_id, row.attempt_id))
        if trace is None:
            _error(
                "CANDIDATE_EVIDENCE_NOT_FOUND",
                "candidate_evidence_fold_trace_missing",
                "candidate evidence fold trace is missing",
                fold_id=str(row.fold_id),
                attempt_id=str(row.attempt_id),
            )
        selection_record = trace.receipt.record(
            FoldSelectionTraceArtifactKind.CANDIDATE_SELECTIONS
        )
        exclusion_record = trace.receipt.record(
            FoldSelectionTraceArtifactKind.CANDIDATE_EXCLUSIONS
        )
        contribution_record = trace.receipt.record(
            FoldSelectionTraceArtifactKind.FACTOR_CONTRIBUTIONS
        )
        fold_id = str(row.fold_id)
        fold_sources.append(
            {
                "attempt_id": str(row.attempt_id),
                "factor_contributions": _record_ref(contribution_record),
                "fold_id": fold_id,
                "candidate_exclusions": _record_ref(exclusion_record),
                "candidate_selections": _record_ref(selection_record),
                "run_id": str(row.run_id),
                "validation_fold_ordinal": row.fold_ordinal,
            }
        )
        selections.extend(
            _selection_item(
                event,
                fold_ordinal=row.fold_ordinal,
                fold_id=fold_id,
                record=selection_record,
            )
            for event in trace.evidence.selections
        )
        exclusions.extend(
            _exclusion_item(
                event,
                fold_ordinal=row.fold_ordinal,
                fold_id=fold_id,
                record=exclusion_record,
            )
            for event in trace.evidence.exclusions
        )
        contributions.extend(
            _contribution_item(
                event,
                fold_ordinal=row.fold_ordinal,
                fold_id=fold_id,
                record=contribution_record,
            )
            for event in trace.evidence.factor_contributions
        )

    selections.sort(
        key=lambda item: (
            item["validation_fold_ordinal"],
            str(item["fold_id"]).encode(),
            str(item["trade_date"]).encode(),
            item["rank"],
            str(item["instrument_id"]).encode(),
        )
    )
    exclusions.sort(
        key=lambda item: (
            item["validation_fold_ordinal"],
            str(item["fold_id"]).encode(),
            str(item["trade_date"]).encode(),
            str(item["instrument_id"]).encode(),
            str(item["stage"]).encode(),
            str(item["reason_code"]).encode(),
        )
    )
    contributions.sort(
        key=lambda item: (
            item["validation_fold_ordinal"],
            str(item["fold_id"]).encode(),
            str(item["trade_date"]).encode(),
            str(item["instrument_id"]).encode(),
            str(item["factor_id"]).encode(),
        )
    )
    return CandidateEvidenceBundle(
        manifest={
            "candidate_id": candidate_id,
            "comparison_payload_hash": str(collected.comparison.content_hash),
            "comparison_revision": comparison_revision,
            "experiment_id": str(rows[0].experiment_id),
        },
        fold_sources=tuple(fold_sources),
        selections=tuple(selections),
        exclusions=tuple(exclusions),
        factor_contributions=tuple(contributions),
    )


def candidate_evidence_bundle_relative_path(bundle: CandidateEvidenceBundle) -> str:
    """Return the stable candidate artifact path within the approved envelope."""
    manifest = bundle.manifest
    return (
        f"experiments/{manifest['experiment_id']}/candidates/"
        f"{manifest['candidate_id']}/candidate-evidence-"
        f"{manifest['comparison_payload_hash']}.json"
    )


class _IndexedJsonArtifactReader(Protocol):
    def read_indexed_json(self, artifact_id: str) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class CandidateEvidencePage:
    """Application-owned typed page over one immutable candidate bundle."""

    candidate_id: str
    experiment_id: str
    artifact_id: str
    content_hash: str
    items: tuple[CandidateEvidenceItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class CandidateEvidenceReader:
    """Resolve only the bundle matching the current comparison content hash."""

    scheduler_store: ExperimentSchedulerStoreProtocol
    walk_forward_assembler: WalkForwardEvidenceAssembler
    artifact_service: _IndexedJsonArtifactReader

    def load_current_bundle(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> tuple[_ArtifactRecord, CandidateEvidenceBundle] | None:
        """Load the current comparison's exact bundle after full verification."""
        typed_experiment_id = ExperimentId(experiment_id)
        snapshot = self.scheduler_store.load_snapshot(typed_experiment_id)
        if not any(
            str(candidate.candidate_id) == candidate_id
            for candidate in snapshot.launch_spec.candidates
        ):
            _error(
                "CANDIDATE_EXPERIMENT_MISMATCH",
                "candidate_experiment_mismatch",
                "candidate does not belong to experiment",
                experiment_id=experiment_id,
                candidate_id=candidate_id,
            )
        events = self.scheduler_store.list_status_events(typed_experiment_id)
        comparison_revision = _current_comparison_revision(events)
        collected = self.walk_forward_assembler.assemble(
            snapshot,
            project_snapshot_manifest(
                read_unique_preflight_detail(events, typed_experiment_id)
            ),
        )
        comparison_hash = str(collected.comparison.content_hash)
        matches = tuple(
            record
            for record in self.scheduler_store.list_experiment_artifacts(
                typed_experiment_id
            )
            if record.artifact_kind == CANDIDATE_EVIDENCE_ARTIFACT_KIND
            and record.candidate_id == CandidateId(candidate_id)
            and isinstance(record.manifest.get("audit"), Mapping)
            and cast("Mapping[str, object]", record.manifest["audit"]).get(
                "comparison_payload_hash"
            )
            == comparison_hash
            and cast("Mapping[str, object]", record.manifest["audit"]).get(
                "comparison_revision"
            )
            == comparison_revision
        )
        if not matches:
            return None
        if len(matches) != 1:
            _error(
                "CANDIDATE_EVIDENCE_INVALID",
                "candidate_evidence_artifact_not_unique",
                "candidate evidence artifact is not unique",
            )
        record = matches[0]
        record_audit = cast("Mapping[str, object]", record.manifest["audit"])
        payload = self.artifact_service.read_indexed_json(record.artifact_id)
        bundle = _decode_bundle(payload)
        if (
            bundle.artifact_id != record.artifact_id
            or bundle.content_hash != str(record.content_hash)
            or bundle.manifest.get("experiment_id") != experiment_id
            or bundle.manifest.get("candidate_id") != candidate_id
            or bundle.manifest.get("comparison_payload_hash") != comparison_hash
            or bundle.manifest.get("comparison_revision") != comparison_revision
            or record_audit.get("comparison_revision") != comparison_revision
            or set(bundle.manifest)
            != {
                "candidate_id",
                "comparison_payload_hash",
                "comparison_revision",
                "experiment_id",
            }
        ):
            _error(
                "CANDIDATE_EVIDENCE_INVALID",
                "candidate_evidence_artifact_identity_drift",
                "candidate evidence artifact identity drifted",
            )
        return record, bundle

    def read_page(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        resource_kind: CandidateEvidenceResourceKind,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CandidateEvidencePage:
        """Read one bounded page with no latest/max lineage inference."""
        if type(limit) is not int or not 1 <= limit <= _MAX_PAGE_LIMIT:
            _error(
                "INVALID_CANDIDATE_EVIDENCE_SCOPE",
                "candidate_evidence_limit_invalid",
                "candidate evidence limit must be between 1 and 100",
            )
        loaded = self.load_current_bundle(experiment_id, candidate_id)
        if loaded is None:
            _error(
                "CANDIDATE_EVIDENCE_NOT_FOUND",
                "candidate_evidence_not_found",
                "candidate evidence was not found",
                experiment_id=experiment_id,
                candidate_id=candidate_id,
            )
        record, bundle = loaded
        offset = 0
        if cursor is not None:
            offset = decode_candidate_evidence_cursor(
                cursor,
                expected_content_hash=bundle.content_hash,
                expected_resource_kind=resource_kind,
            ).offset
        items = bundle.items(resource_kind)
        if offset > len(items):
            _error(
                "INVALID_CANDIDATE_EVIDENCE_CURSOR",
                "candidate_evidence_cursor_offset_out_of_range",
                "candidate evidence cursor is invalid",
            )
        end = min(offset + limit, len(items))
        next_cursor = (
            None
            if end == len(items)
            else encode_candidate_evidence_cursor(
                content_hash=bundle.content_hash,
                resource_kind=resource_kind,
                offset=end,
            )
        )
        return CandidateEvidencePage(
            candidate_id=candidate_id,
            experiment_id=experiment_id,
            artifact_id=record.artifact_id,
            content_hash=str(record.content_hash),
            items=items[offset:end],
            next_cursor=next_cursor,
        )


def _mapping_tuple(value: object, *, field: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_payload_invalid",
            "candidate evidence payload is invalid",
            field=field,
        )
    result = tuple(cast("Sequence[object]", value))
    if any(not isinstance(item, Mapping) for item in result):
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_payload_invalid",
            "candidate evidence payload is invalid",
            field=field,
        )
    return cast("tuple[Mapping[str, object], ...]", result)


def _decode_bundle(payload: Mapping[str, object]) -> CandidateEvidenceBundle:
    if (
        set(payload)
        != {
            "fold_sources",
            "manifest",
            "resources",
            "schema_id",
            "schema_version",
        }
        or payload.get("schema_id") != CANDIDATE_EVIDENCE_SCHEMA_ID
        or payload.get("schema_version") != CANDIDATE_EVIDENCE_SCHEMA_VERSION
        or not isinstance(payload.get("manifest"), Mapping)
        or not isinstance(payload.get("resources"), Mapping)
    ):
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_payload_invalid",
            "candidate evidence payload is invalid",
        )
    resources = cast("Mapping[str, object]", payload["resources"])
    if set(resources) != {
        "exclusions",
        "factor_contributions",
        "selections",
    }:
        _error(
            "CANDIDATE_EVIDENCE_INVALID",
            "candidate_evidence_payload_invalid",
            "candidate evidence payload is invalid",
        )
    return CandidateEvidenceBundle(
        manifest=cast("Mapping[str, object]", payload["manifest"]),
        fold_sources=_mapping_tuple(payload["fold_sources"], field="fold_sources"),
        selections=_mapping_tuple(resources["selections"], field="selections"),
        exclusions=_mapping_tuple(resources["exclusions"], field="exclusions"),
        factor_contributions=_mapping_tuple(
            resources["factor_contributions"],
            field="factor_contributions",
        ),
    )
