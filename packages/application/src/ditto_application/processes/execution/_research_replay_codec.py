"""Strict R3 replay marker and manifest codecs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from ditto_backtest.config import validate_spec_hash
from ditto_backtest.manifest import InputRef, RuleRef, RunManifest, RunMode
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_strategy.models import StrategyArtifactRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.replay_manifest_codec import (
    deserialize_effective_parameters,
)

RESEARCH_REPLAY_EVIDENCE_VERSION = 1
RUN_MANIFEST_ARTIFACT_KIND = "run_manifest"
_RESEARCH_REPLAY_MARKER = "research_replay_evidence_version"
_RESEARCH_REPLAY_BUNDLE = "research_replay_bundle"
_POINTER_KEYS = {
    "schema_version",
    "manifest_artifact_id",
    "report_artifact_id",
    "required_artifact_ids",
    "fill_log_artifact_id",
}
_EVIDENCE_KEYS = {
    "schema_version",
    "reproduction_fingerprint",
    "key_result_summary_artifact_id",
    "required_artifacts",
}
_ARTIFACT_KEYS = {
    "artifact_id",
    "artifact_kind",
    "artifact_format",
    "content_hash",
    "schema_hash",
    "row_count",
    "byte_size",
}


@dataclass(frozen=True, slots=True)
class ResearchReplayBundlePointer:
    """Exact artifact identities persisted on a strategy run record."""

    schema_version: int
    manifest_artifact_id: str
    report_artifact_id: str
    required_artifact_ids: tuple[str, ...]
    fill_log_artifact_id: str | None


def build_research_replay_metadata(
    *,
    manifest_artifact: ReplayArtifactRef,
    replay_evidence: ResearchReplayEvidence,
    fill_log_artifact_id: str | None = None,
) -> dict[str, object]:
    """Build a strict pointer from already-authoritative replay evidence."""
    if (
        manifest_artifact.artifact_kind != RUN_MANIFEST_ARTIFACT_KIND
        or manifest_artifact.artifact_format != "json"
    ):
        raise ValueError("manifest_artifact must be a run_manifest JSON artifact")
    required_ids = tuple(
        item.artifact_id for item in replay_evidence.required_artifacts
    )
    if manifest_artifact.artifact_id in set(required_ids):
        raise ValueError("manifest artifact must be separate from required results")
    if fill_log_artifact_id is not None and fill_log_artifact_id not in set(
        required_ids
    ):
        raise ValueError("fill_log_artifact_id must reference one required artifact")
    return {
        _RESEARCH_REPLAY_MARKER: RESEARCH_REPLAY_EVIDENCE_VERSION,
        _RESEARCH_REPLAY_BUNDLE: {
            "schema_version": RESEARCH_REPLAY_EVIDENCE_VERSION,
            "manifest_artifact_id": manifest_artifact.artifact_id,
            "report_artifact_id": replay_evidence.key_result_summary_artifact_id,
            "required_artifact_ids": list(required_ids),
            "fill_log_artifact_id": fill_log_artifact_id,
        },
    }


def research_replay_pointer(
    record: StrategyArtifactRecord,
) -> ResearchReplayBundlePointer | None:
    """Decode one supported pointer while distinguishing absence from corruption."""
    metadata = record.metadata
    has_marker = _RESEARCH_REPLAY_MARKER in metadata
    has_bundle = _RESEARCH_REPLAY_BUNDLE in metadata
    if not has_marker and not has_bundle:
        return None
    if not has_marker or not has_bundle:
        _marker_error(record, "marker and bundle pointer must be persisted together")
    marker = metadata[_RESEARCH_REPLAY_MARKER]
    if type(marker) is not int or marker != RESEARCH_REPLAY_EVIDENCE_VERSION:
        raise AppProcessError(
            "unsupported research replay evidence version",
            reason="unsupported_replay_evidence_version",
            run_id=record.run_id,
            version=marker,
        )
    bundle = _bundle_mapping(metadata[_RESEARCH_REPLAY_BUNDLE], record)
    schema_version = bundle["schema_version"]
    if type(schema_version) is not int or schema_version != marker:
        _marker_error(record, "bundle schema version is invalid")
    schema_version = cast(int, schema_version)
    manifest_id = _pointer_identity(
        bundle["manifest_artifact_id"], "manifest_artifact_id", record.run_id
    )
    report_id = _pointer_identity(
        bundle["report_artifact_id"], "report_artifact_id", record.run_id
    )
    required_ids = _required_ids(bundle["required_artifact_ids"], record)
    fill_id = _optional_pointer_identity(
        bundle["fill_log_artifact_id"], "fill_log_artifact_id", record.run_id
    )
    _validate_pointer_membership(
        record,
        manifest_id=manifest_id,
        report_id=report_id,
        required_ids=required_ids,
        fill_id=fill_id,
    )
    return ResearchReplayBundlePointer(
        schema_version=schema_version,
        manifest_artifact_id=manifest_id,
        report_artifact_id=report_id,
        required_artifact_ids=required_ids,
        fill_log_artifact_id=fill_id,
    )


def _marker_error(record: StrategyArtifactRecord, message: str) -> None:
    raise AppProcessError(
        f"research replay {message}",
        reason="invalid_replay_evidence_marker",
        run_id=record.run_id,
    )


def _bundle_mapping(
    raw: object,
    record: StrategyArtifactRecord,
) -> Mapping[object, object]:
    if not isinstance(raw, Mapping):
        _marker_error(record, "bundle pointer must be an object")
    bundle = cast(Mapping[object, object], raw)
    if set(bundle) != _POINTER_KEYS:
        _marker_error(record, "bundle pointer fields do not match Schema v1")
    return bundle


def _required_ids(raw: object, record: StrategyArtifactRecord) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        _marker_error(record, "required_artifact_ids must be a non-empty array")
    identities = tuple(
        _pointer_identity(item, "required_artifact_ids", record.run_id)
        for item in cast(list[object], raw)
    )
    if len(set(identities)) != len(identities):
        _marker_error(record, "required_artifact_ids must be unique")
    return identities


def _validate_pointer_membership(
    record: StrategyArtifactRecord,
    *,
    manifest_id: str,
    report_id: str,
    required_ids: tuple[str, ...],
    fill_id: str | None,
) -> None:
    required = set(required_ids)
    if manifest_id in required:
        _marker_error(record, "manifest artifact must be separate from results")
    if report_id not in required:
        _marker_error(record, "report artifact must be one of the required artifacts")
    if fill_id is not None and fill_id not in required:
        _marker_error(record, "fill log artifact must be one of the required artifacts")


def _pointer_identity(value: object, field_name: str, run_id: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "/" in value
        or "\\" in value
    ):
        raise AppProcessError(
            f"{field_name} must be a canonical identity",
            reason="invalid_replay_evidence_marker",
            run_id=run_id,
        )
    return value


def _optional_pointer_identity(
    value: object,
    field_name: str,
    run_id: str,
) -> str | None:
    return None if value is None else _pointer_identity(value, field_name, run_id)


def deserialize_manifest(raw: dict[str, Any]) -> RunManifest:
    """Deserialize a persisted manifest without weakening reproduction identity."""
    required_identity_fields = (
        "spec_hash",
        "base_spec_hash",
        "parameter_hash",
        "effective_parameters",
        "research_snapshot_id",
        "research_snapshot_manifest_hash",
    )
    for field_name in required_identity_fields:
        if field_name not in raw:
            raise AppProcessError(
                f"manifest missing required identity field: {field_name}",
                field_name=field_name,
                reason="missing_reproduction_identity",
            )
    try:
        spec_hash = validate_spec_hash(raw["spec_hash"])
    except ValueError as exc:
        raise AppProcessError(
            str(exc),
            field_name="spec_hash",
            reason="invalid_canonical_identity",
        ) from exc
    inputs = tuple(
        InputRef(
            instrument_id=item["instrument_id"],
            data_hash=item.get("data_hash", ""),
            date_range=tuple(item.get("date_range", ("", ""))),
            source=item.get("source", ""),
            source_snapshot_id=item.get("source_snapshot_id", ""),
        )
        for item in raw.get("input_ref_details", [])
    )
    rules = tuple(
        RuleRef(
            instrument_id=item["instrument_id"],
            definition_version=item.get("definition_version", ""),
            trading_rule_as_of=item.get("trading_rule_as_of", ""),
            fee_schedule_as_of=item.get("fee_schedule_as_of", ""),
            trading_rule_effective_to=item.get("trading_rule_effective_to", ""),
            fee_schedule_effective_to=item.get("fee_schedule_effective_to", ""),
        )
        for item in raw.get("rule_refs", [])
    )
    try:
        return RunManifest(
            run_id=raw.get("run_id", ""),
            strategy_id=raw.get("strategy_id", ""),
            strategy_version=raw.get("strategy_version", ""),
            mode=RunMode(raw.get("mode", "backtest")),
            created_at=raw.get("created_at", ""),
            input_refs=tuple(raw.get("input_refs", ())),
            input_ref_details=inputs,
            parameter_overrides=tuple(raw.get("parameter_overrides", ())),
            rule_refs=rules,
            artifacts=tuple(raw.get("artifacts", ())),
            config_hash=raw.get("config_hash", ""),
            engine_version=raw.get("engine_version", ""),
            rule_resolution_policy=raw.get("rule_resolution_policy", "as_of_date"),
            universe_hash=raw.get("universe_hash", ""),
            spec_hash=spec_hash,
            base_spec_hash=raw["base_spec_hash"],
            parameter_hash=raw["parameter_hash"],
            effective_parameters=deserialize_effective_parameters(
                raw["effective_parameters"]
            ),
            research_snapshot_id=raw["research_snapshot_id"],
            research_snapshot_manifest_hash=raw["research_snapshot_manifest_hash"],
            dependency_versions=tuple(raw.get("dependency_versions", ())),
            random_seed=raw.get("random_seed"),
            pit_time_column=raw.get("pit_time_column", "knowledge_date"),
            pit_policy=raw.get("pit_policy", "knowledge_date_fail_closed"),
            unsafe_time_policy=raw.get("unsafe_time_policy", ""),
            knowledge_lag_days=raw.get("knowledge_lag_days", 1),
            replay_evidence=_deserialize_replay_evidence(raw.get("replay_evidence")),
        )
    except (TypeError, ValueError) as exc:
        raise AppProcessError(
            str(exc),
            reason="invalid_reproduction_identity",
        ) from exc


def _deserialize_replay_evidence(raw: object) -> ResearchReplayEvidence | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _evidence_error("replay_evidence must be a JSON object")
    value = cast(dict[object, object], raw)
    if set(value) != _EVIDENCE_KEYS:
        _evidence_error("replay_evidence fields do not match Schema v1")
    schema_version = value["schema_version"]
    if type(schema_version) is not int:
        _evidence_error("replay_evidence schema_version must be an exact integer")
    schema_version = cast(int, schema_version)
    raw_artifacts = value["required_artifacts"]
    if not isinstance(raw_artifacts, list):
        _evidence_error("replay_evidence required_artifacts must be an array")
    artifacts = tuple(
        _deserialize_replay_artifact(item, index=index)
        for index, item in enumerate(cast(list[object], raw_artifacts))
    )
    try:
        return ResearchReplayEvidence(
            schema_version=schema_version,
            reproduction_fingerprint=_evidence_str(value, "reproduction_fingerprint"),
            key_result_summary_artifact_id=_evidence_str(
                value, "key_result_summary_artifact_id"
            ),
            required_artifacts=artifacts,
        )
    except ValueError as exc:
        raise AppProcessError(
            str(exc),
            reason="invalid_replay_evidence",
        ) from exc


def _deserialize_replay_artifact(raw: object, *, index: int) -> ReplayArtifactRef:
    if not isinstance(raw, dict):
        _evidence_error(f"required_artifacts[{index}] must be an object")
    item = cast(dict[object, object], raw)
    if set(item) != _ARTIFACT_KEYS:
        _evidence_error(f"required_artifacts[{index}] fields do not match Schema v1")
    try:
        return ReplayArtifactRef(
            artifact_id=_evidence_str(item, "artifact_id"),
            artifact_kind=_evidence_str(item, "artifact_kind"),
            artifact_format=_evidence_str(item, "artifact_format"),
            content_hash=_evidence_str(item, "content_hash"),
            schema_hash=_evidence_str(item, "schema_hash"),
            row_count=_evidence_int(item, "row_count"),
            byte_size=_evidence_int(item, "byte_size"),
        )
    except ValueError as exc:
        raise AppProcessError(
            str(exc),
            reason="invalid_replay_evidence",
        ) from exc


def _evidence_error(message: str) -> None:
    raise AppProcessError(message, reason="invalid_replay_evidence")


def _evidence_str(payload: Mapping[object, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _evidence_int(payload: Mapping[object, object], field_name: str) -> int:
    value = payload[field_name]
    if type(value) is not int:
        raise ValueError(f"{field_name} must be an exact integer")
    return value
