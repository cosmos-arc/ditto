"""Index-backed verified artifact boundary for R3 replay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol, cast

import polars as pl
from ditto_analysis.experiments import ArtifactRecord
from ditto_backtest.config import validate_canonical_sha256
from ditto_backtest.manifest_types import ReplayArtifactRef
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting.fills import FillEvent
from ditto_strategy.models import ArtifactKind
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution._research_replay_codec import (
    RESEARCH_REPLAY_EVIDENCE_VERSION,
    RUN_MANIFEST_ARTIFACT_KIND,
    ResearchReplayBundlePointer,
    research_replay_pointer,
)
from ditto_application.queries.artifact_utils import find_artifact

# Reuse the analysis-owned frozen ``ArtifactRecord`` directly instead of
# mirroring a second mutable protocol; the verified-read boundary only needs
# its immutable Schema v1 fields.
type IndexedArtifactRecord = ArtifactRecord


class IndexedArtifactRecordReader(Protocol):
    """Narrow Schema v1 metadata port used by the application adapter."""

    def get_artifact(self, artifact_id: str) -> IndexedArtifactRecord | None:
        """Return one immutable indexed artifact record."""
        ...


class IndexedArtifactContentReader(Protocol):
    """Narrow verified-content port owned by the analysis artifact service."""

    def read_indexed_json(self, artifact_id: str) -> dict[str, object]:
        """Return JSON after full index, sidecar, and byte verification."""
        ...

    def read_indexed_parquet(self, artifact_id: str) -> pl.DataFrame:
        """Return Parquet after full index, sidecar, and byte verification."""
        ...


@dataclass(frozen=True, slots=True)
class VerifiedReplayBundle:
    """One run bundle returned only after index and file re-verification."""

    run_id: str
    manifest_payload: Mapping[str, object]
    report_payload: Mapping[str, object]
    manifest_artifact: ReplayArtifactRef
    reproduction_fingerprint: str
    report_artifact_id: str
    verified_artifacts: tuple[ReplayArtifactRef, ...]
    fill_log: tuple[FillEvent, ...] | None = None
    fill_log_artifact_id: str | None = None
    schema_version: int = RESEARCH_REPLAY_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous verified-read claims."""
        _validate_bundle_header(self)
        _validate_bundle_artifacts(self)
        _validate_bundle_fill(self)


def _validate_bundle_header(bundle: VerifiedReplayBundle) -> None:
    if type(bundle.schema_version) is not int or (
        bundle.schema_version != RESEARCH_REPLAY_EVIDENCE_VERSION
    ):
        raise AppProcessError(
            "unsupported verified replay bundle schema_version",
            reason="invalid_verified_replay_bundle",
        )
    if not bundle.run_id or bundle.run_id != bundle.run_id.strip():
        raise AppProcessError(
            "verified replay bundle run_id must be canonical",
            reason="invalid_verified_replay_bundle",
        )
    if not isinstance(cast(object, bundle.manifest_payload), Mapping) or not isinstance(
        cast(object, bundle.report_payload), Mapping
    ):
        raise AppProcessError(
            "verified replay JSON payloads must be mappings",
            reason="invalid_verified_replay_bundle",
        )
    if type(bundle.manifest_artifact) is not ReplayArtifactRef or (
        bundle.manifest_artifact.artifact_kind != RUN_MANIFEST_ARTIFACT_KIND
        or bundle.manifest_artifact.artifact_format != "json"
    ):
        raise AppProcessError(
            "manifest_artifact must be one verified run_manifest JSON artifact",
            reason="invalid_verified_replay_bundle",
        )
    validate_canonical_sha256(
        bundle.reproduction_fingerprint,
        field_name="reproduction_fingerprint",
    )
    if not bundle.report_artifact_id or (
        bundle.report_artifact_id != bundle.report_artifact_id.strip()
    ):
        raise AppProcessError(
            "report_artifact_id must be canonical",
            reason="invalid_verified_replay_bundle",
        )


def _validate_bundle_artifacts(bundle: VerifiedReplayBundle) -> None:
    if not isinstance(cast(object, bundle.verified_artifacts), tuple) or not (
        bundle.verified_artifacts
    ):
        raise AppProcessError(
            "verified_artifacts must be a non-empty tuple",
            reason="invalid_verified_replay_bundle",
        )
    if any(type(item) is not ReplayArtifactRef for item in bundle.verified_artifacts):
        raise AppProcessError(
            "verified_artifacts must contain exact ReplayArtifactRef values",
            reason="invalid_verified_replay_bundle",
        )
    verified_ids = tuple(item.artifact_id for item in bundle.verified_artifacts)
    if len(set(verified_ids)) != len(verified_ids):
        raise AppProcessError(
            "verified artifact IDs must be unique",
            reason="invalid_verified_replay_bundle",
        )
    if bundle.manifest_artifact.artifact_id in set(verified_ids):
        raise AppProcessError(
            "manifest artifact must be separate from replay result artifacts",
            reason="invalid_verified_replay_bundle",
        )


def _validate_bundle_fill(bundle: VerifiedReplayBundle) -> None:
    if bundle.fill_log is not None and not isinstance(
        cast(object, bundle.fill_log), tuple
    ):
        raise AppProcessError(
            "fill_log must be an immutable tuple when present",
            reason="invalid_verified_replay_bundle",
        )
    if (bundle.fill_log is None) != (bundle.fill_log_artifact_id is None):
        raise AppProcessError(
            "fill_log and fill_log_artifact_id must be provided together",
            reason="invalid_verified_replay_bundle",
        )


class VerifiedReplayArtifactReader(Protocol):
    """Application-owned port for a fully verified indexed run bundle."""

    def read_bundle(self, run_id: str) -> VerifiedReplayBundle:
        """Read a run only after verifying every indexed measurement."""
        ...


@dataclass(frozen=True, slots=True)
class _ManifestAnchor:
    ref: ReplayArtifactRef
    payload: dict[str, object]
    lineage: tuple[object, object, object, object]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _RequiredArtifacts:
    refs: tuple[ReplayArtifactRef, ...]
    report: dict[str, object]
    fill_log: tuple[FillEvent, ...] | None


class IndexedResearchReplayArtifactReader:
    """Resolve an R3 marker into one same-attempt verified bundle."""

    def __init__(
        self,
        *,
        strategy_artifact_service: StrategyArtifactService,
        artifact_index_reader: IndexedArtifactRecordReader,
        artifact_content_reader: IndexedArtifactContentReader,
    ) -> None:
        self._strategy_artifact_service = strategy_artifact_service
        self._artifact_index_reader = artifact_index_reader
        self._artifact_content_reader = artifact_content_reader

    def read_bundle(self, run_id: str) -> VerifiedReplayBundle:
        """Read every explicitly named artifact through verified indexed APIs."""
        pointer = self._pointer(run_id)
        anchor = self._manifest_anchor(run_id, pointer)
        required = self._required_artifacts(run_id, pointer, anchor)
        _validate_report_run_id(required.report, run_id)
        if pointer.fill_log_artifact_id is not None and required.fill_log is None:
            _mismatch(run_id, "fill pointer is not a required Parquet artifact")
        return VerifiedReplayBundle(
            run_id=run_id,
            manifest_payload=anchor.payload,
            report_payload=required.report,
            manifest_artifact=anchor.ref,
            reproduction_fingerprint=anchor.fingerprint,
            report_artifact_id=pointer.report_artifact_id,
            verified_artifacts=required.refs,
            fill_log=required.fill_log,
            fill_log_artifact_id=pointer.fill_log_artifact_id,
        )

    def _pointer(self, run_id: str) -> ResearchReplayBundlePointer:
        record = find_artifact(
            self._strategy_artifact_service,
            run_id,
            ArtifactKind.BACKTEST_REPORT,
        )
        if record is None:
            raise FileNotFoundError(f"Artifact directory not found for run: {run_id}")
        pointer = research_replay_pointer(record)
        if pointer is None:
            raise AppProcessError(
                "indexed replay reader requires an R3 strategy artifact marker",
                reason="r3_replay_index_marker_missing",
                run_id=run_id,
            )
        return pointer

    def _manifest_anchor(
        self,
        run_id: str,
        pointer: ResearchReplayBundlePointer,
    ) -> _ManifestAnchor:
        record = self._indexed_record(pointer.manifest_artifact_id)
        ref, payload = self._read_json_artifact(pointer.manifest_artifact_id)
        if ref.artifact_kind != RUN_MANIFEST_ARTIFACT_KIND:
            _mismatch(run_id, "manifest pointer is not a run_manifest artifact")
        if payload.get("run_id") != run_id:
            _mismatch(run_id, "verified run manifest identifies another run")
        return _ManifestAnchor(
            ref=ref,
            payload=payload,
            lineage=_record_lineage(
                record,
                run_id=run_id,
                artifact_id=pointer.manifest_artifact_id,
            ),
            fingerprint=_record_fingerprint(
                record,
                artifact_id=pointer.manifest_artifact_id,
            ),
        )

    def _required_artifacts(
        self,
        run_id: str,
        pointer: ResearchReplayBundlePointer,
        anchor: _ManifestAnchor,
    ) -> _RequiredArtifacts:
        refs: list[ReplayArtifactRef] = []
        report: dict[str, object] | None = None
        fill_log: tuple[FillEvent, ...] | None = None
        for artifact_id in pointer.required_artifact_ids:
            record = self._indexed_record(artifact_id)
            self._validate_same_source(record, artifact_id, run_id, anchor)
            ref, payload = self._read_required(artifact_id)
            refs.append(ref)
            if artifact_id == pointer.report_artifact_id:
                report = _require_json_payload(payload, run_id)
            if artifact_id == pointer.fill_log_artifact_id:
                fill_log = _require_fill_payload(payload, run_id)
        if report is None:
            _mismatch(run_id, "report pointer is not a required JSON artifact")
        return _RequiredArtifacts(tuple(refs), report, fill_log)

    def _validate_same_source(
        self,
        record: IndexedArtifactRecord,
        artifact_id: str,
        run_id: str,
        anchor: _ManifestAnchor,
    ) -> None:
        lineage = _record_lineage(record, run_id=run_id, artifact_id=artifact_id)
        if lineage != anchor.lineage:
            _mismatch(run_id, "artifacts do not share exact typed lineage", artifact_id)
        if _record_fingerprint(record, artifact_id=artifact_id) != anchor.fingerprint:
            _mismatch(run_id, "artifacts disagree on fingerprint", artifact_id)

    def _read_required(
        self,
        artifact_id: str,
    ) -> tuple[ReplayArtifactRef, dict[str, object] | pl.DataFrame]:
        if self._indexed_artifact_format(artifact_id) == "json":
            return self._read_json_artifact(artifact_id)
        return self._read_parquet_artifact(artifact_id)

    def _indexed_record(self, artifact_id: str) -> IndexedArtifactRecord:
        record = self._artifact_index_reader.get_artifact(artifact_id)
        if record is None:
            raise AppProcessError(
                "R3 replay artifact is missing from the Schema v1 index",
                reason="verified_replay_artifact_missing",
                artifact_id=artifact_id,
            )
        return record

    def _indexed_artifact_format(self, artifact_id: str) -> str:
        manifest = self._indexed_record(artifact_id).manifest
        artifact_format = manifest.get("format")
        if artifact_format not in {"json", "parquet"}:
            _mismatch("", "indexed artifact format is unsupported", artifact_id)
        return cast(str, artifact_format)

    def _artifact_ref(self, artifact_id: str) -> ReplayArtifactRef:
        record = self._indexed_record(artifact_id)
        try:
            if record.artifact_id != artifact_id:
                raise AppProcessError(
                    "indexed artifact identity mismatch",
                    reason="verified_replay_evidence_mismatch",
                    artifact_id=artifact_id,
                )
            return ReplayArtifactRef(
                artifact_id=record.artifact_id,
                artifact_kind=record.artifact_kind,
                artifact_format=self._indexed_artifact_format(artifact_id),
                content_hash=str(record.content_hash),
                schema_hash=str(record.schema_hash),
                row_count=record.row_count,
                byte_size=record.byte_size,
            )
        except (TypeError, ValueError) as exc:
            raise AppProcessError(
                "indexed replay artifact measurements are invalid",
                reason="verified_replay_evidence_mismatch",
                artifact_id=artifact_id,
            ) from exc

    def _read_json_artifact(
        self,
        artifact_id: str,
    ) -> tuple[ReplayArtifactRef, dict[str, object]]:
        if self._indexed_artifact_format(artifact_id) != "json":
            _mismatch("", "indexed JSON pointer has the wrong format", artifact_id)
        payload = self._artifact_content_reader.read_indexed_json(artifact_id)
        return self._artifact_ref(artifact_id), payload

    def _read_parquet_artifact(
        self,
        artifact_id: str,
    ) -> tuple[ReplayArtifactRef, pl.DataFrame]:
        if self._indexed_artifact_format(artifact_id) != "parquet":
            _mismatch("", "indexed Parquet pointer has the wrong format", artifact_id)
        frame = self._artifact_content_reader.read_indexed_parquet(artifact_id)
        return self._artifact_ref(artifact_id), frame


def _record_fingerprint(record: IndexedArtifactRecord, *, artifact_id: str) -> str:
    try:
        fingerprint = str(record.reproduction_fingerprint)
        validate_canonical_sha256(
            fingerprint,
            field_name="reproduction_fingerprint",
        )
    except (TypeError, ValueError) as exc:
        raise AppProcessError(
            "indexed replay artifact fingerprint is invalid",
            reason="verified_replay_evidence_mismatch",
            artifact_id=artifact_id,
        ) from exc
    return fingerprint


def _record_lineage(
    record: IndexedArtifactRecord,
    *,
    run_id: str,
    artifact_id: str,
) -> tuple[object, object, object, object]:
    lineage = (
        record.experiment_id,
        record.candidate_id,
        record.fold_id,
        record.attempt_id,
    )
    audit_value = record.manifest.get("audit")
    valid_audit = False
    if isinstance(audit_value, Mapping):
        audit = cast(Mapping[object, object], audit_value)
        valid_audit = audit.get("run_id") == run_id and audit.get("attempt_id") == str(
            record.attempt_id
        )
    if any(item is None for item in lineage) or not valid_audit:
        raise AppProcessError(
            "indexed replay artifact source lineage is invalid",
            reason="verified_replay_evidence_mismatch",
            run_id=run_id,
            artifact_id=artifact_id,
        )
    return lineage


def _require_json_payload(
    payload: dict[str, object] | pl.DataFrame,
    run_id: str,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        _mismatch(run_id, "report pointer is not JSON")
    return payload


def _require_fill_payload(
    payload: dict[str, object] | pl.DataFrame,
    run_id: str,
) -> tuple[FillEvent, ...]:
    if not isinstance(payload, pl.DataFrame):
        _mismatch(run_id, "fill pointer is not Parquet")
    rows = cast(list[dict[str, object]], payload.to_dicts())
    return tuple(fill_from_indexed_row(row) for row in rows)


def _validate_report_run_id(report: Mapping[str, object], run_id: str) -> None:
    if "run_id" in report and report["run_id"] != run_id:
        _mismatch(run_id, "verified replay report identifies a different run")


def _mismatch(run_id: str, message: str, artifact_id: str = "") -> NoReturn:
    raise AppProcessError(
        f"verified replay evidence mismatch: {message}",
        reason="verified_replay_evidence_mismatch",
        run_id=run_id,
        artifact_id=artifact_id,
    )


def fill_from_indexed_row(row: dict[str, object]) -> FillEvent:
    correlation_id_raw = row.get("correlation_id")
    correlation_id = str(correlation_id_raw) if correlation_id_raw is not None else None
    return FillEvent(
        fill_id=str(row["fill_id"]),
        order_id=str(row["order_id"]),
        instrument_id=InstrumentId(int(cast(int | str, row["instrument_id"]))),
        direction=OrderSide(str(row["direction"])),
        filled_quantity=int(cast(int | str, row["filled_quantity"])),
        fill_price=float(cast(float | int | str, row["fill_price"])),
        fee=float(cast(float | int | str, row["fee"])),
        slippage=float(cast(float | int | str, row["slippage"])),
        event_time=_parse_fill_event_time(row["event_time"]),
        cumulative_quantity=int(cast(int | str, row["cumulative_quantity"])),
        leaves_quantity=int(cast(int | str, row["leaves_quantity"])),
        correlation_id=correlation_id,
    )


def _parse_fill_event_time(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppProcessError(
                f"Unsupported fill event_time value: {value!r}"
            ) from exc
    raise AppProcessError(f"Unsupported fill event_time value: {value!r}")
