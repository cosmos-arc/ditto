"""Resolve one exact R2 live report and its four-group content manifest."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import orjson
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    R2LiveGateArtifactSource,
    R2LiveGateEvidenceSource,
)

__all__ = ["load_r2_live_gate_source"]

_SOURCE_MANIFEST_SCHEMA = "ditto.r2-live-gate-source"
_MAX_SOURCE_MANIFEST_BYTES = 1024 * 1024
_SHA256_HEX_LENGTH = 64


def _content_hash(value: object) -> str | None:
    if (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    ):
        return value
    return None


def _manifest_entry(root: Path, value: object) -> tuple[Path, str] | None:
    payload = cast("dict[object, object]", value) if type(value) is dict else None
    if payload is None or set(payload) != {"relative_path", "sha256"}:
        return None
    relative = payload.get("relative_path")
    content_hash = _content_hash(payload.get("sha256"))
    if type(relative) is not str or not relative or content_hash is None:
        return None
    relative_path = Path(relative)
    candidate = root / relative_path
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or candidate.is_symlink()
    ):
        return None
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved, content_hash


def _artifact_group(
    root: Path,
    value: object,
) -> tuple[R2LiveGateArtifactSource, ...] | None:
    if type(value) is not list or not value:
        return None
    sources: list[R2LiveGateArtifactSource] = []
    for item in cast("list[object]", value):
        entry = _manifest_entry(root, item)
        if entry is None:
            return None
        path, content_hash = entry
        sources.append(
            R2LiveGateArtifactSource(
                path=path,
                artifact_uri=path.as_uri(),
                expected_content_hash=content_hash,
            )
        )
    return tuple(sources)


def _read_source_manifest(source_manifest: Path) -> dict[object, object] | None:
    if source_manifest.is_symlink():
        return None
    try:
        metadata = source_manifest.stat()
        if metadata.st_size <= 0 or metadata.st_size > _MAX_SOURCE_MANIFEST_BYTES:
            return None
        decoded = orjson.loads(source_manifest.read_bytes())
    except (OSError, orjson.JSONDecodeError):
        return None
    if type(decoded) is not dict:
        return None
    return cast("dict[object, object]", decoded)


def _source_manifest_shape(
    payload: dict[object, object],
) -> tuple[object, dict[object, object]] | None:
    groups = payload.get("groups")
    if set(payload) != {"schema", "version", "report", "groups"}:
        return None
    if payload.get("schema") != _SOURCE_MANIFEST_SCHEMA:
        return None
    if type(payload.get("version")) is not int or payload.get("version") != 1:
        return None
    if type(groups) is not dict:
        return None
    group_payload = cast("dict[object, object]", groups)
    if set(group_payload) != {
        "provider_entitlement",
        "performance",
        "recoverability",
        "idempotency",
    }:
        return None
    return payload.get("report"), group_payload


def _resolved_report_entry(
    *,
    root: Path,
    value: object,
    report_path: Path,
) -> tuple[Path, str] | None:
    report = _manifest_entry(root, value)
    if report is None:
        return None
    report_file, _ = report
    try:
        matches = report_file == report_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return report if matches else None


def load_r2_live_gate_source(
    *,
    report_path: Path,
    source_manifest: Path,
) -> R2LiveGateEvidenceSource | None:
    """Resolve one exact R2 report and its four-group content manifest."""
    payload = _read_source_manifest(source_manifest)
    if payload is None:
        return None
    shape = _source_manifest_shape(payload)
    if shape is None:
        return None
    report_value, group_payload = shape
    root = source_manifest.parent
    report = _resolved_report_entry(
        root=root,
        value=report_value,
        report_path=report_path,
    )
    if report is None:
        return None
    report_file, report_hash = report
    provider = _artifact_group(root, group_payload.get("provider_entitlement"))
    performance = _artifact_group(root, group_payload.get("performance"))
    recoverability = _artifact_group(root, group_payload.get("recoverability"))
    idempotency = _artifact_group(root, group_payload.get("idempotency"))
    groups = (provider, performance, recoverability, idempotency)
    if any(group is None for group in groups):
        return None
    try:
        return R2LiveGateEvidenceSource(
            report_path=report_file,
            report_uri=report_file.as_uri(),
            expected_report_hash=report_hash,
            provider_entitlement_artifacts=cast(
                "tuple[R2LiveGateArtifactSource, ...]", provider
            ),
            performance_artifacts=cast(
                "tuple[R2LiveGateArtifactSource, ...]", performance
            ),
            recoverability_artifacts=cast(
                "tuple[R2LiveGateArtifactSource, ...]", recoverability
            ),
            idempotency_artifacts=cast(
                "tuple[R2LiveGateArtifactSource, ...]", idempotency
            ),
        )
    except AppProcessError:
        return None
