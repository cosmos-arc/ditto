"""Authenticated machine-readable manifests for workstation release gates."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import orjson

type GateName = Literal["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
type GateStatus = Literal["passed", "blocked"]

_SCHEMA_VERSION = 1


class EvidenceManifestError(RuntimeError):
    """Raised when Gate evidence cannot be authenticated exactly."""


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """One immutable file included in a Gate decision."""

    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GateEvidenceManifest:
    """Decision record whose hash covers artifacts and explicit blockers."""

    schema_version: int
    gate: GateName
    status: GateStatus
    artifacts: tuple[EvidenceArtifact, ...]
    blockers: tuple[str, ...]
    manifest_hash: str


def build_gate_manifest(
    evidence_root: Path,
    gate: GateName,
    artifact_paths: tuple[Path, ...],
    *,
    blockers: tuple[str, ...] = (),
) -> GateEvidenceManifest:
    """Hash exact evidence files and derive a fail-closed Gate decision."""
    root = evidence_root.expanduser().resolve(strict=False)
    if gate not in {"Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}:
        raise EvidenceManifestError("gate is invalid")
    normalized_blockers = tuple(item.strip() for item in blockers)
    if any(not item for item in normalized_blockers):
        raise EvidenceManifestError("blockers must be non-empty strings")
    artifacts = tuple(
        sorted(
            (_artifact(root, path) for path in artifact_paths),
            key=lambda item: item.relative_path,
        )
    )
    if not artifacts:
        raise EvidenceManifestError("at least one evidence artifact is required")
    if len({item.relative_path for item in artifacts}) != len(artifacts):
        raise EvidenceManifestError("evidence artifact paths must be unique")
    status: GateStatus = "blocked" if normalized_blockers else "passed"
    payload = _payload(gate, status, artifacts, normalized_blockers)
    return GateEvidenceManifest(
        schema_version=_SCHEMA_VERSION,
        gate=gate,
        status=status,
        artifacts=artifacts,
        blockers=normalized_blockers,
        manifest_hash=_digest(payload),
    )


def write_gate_manifest(path: Path, manifest: GateEvidenceManifest) -> None:
    """Persist one manifest without weakening its authenticated payload."""
    destination = path.expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        orjson.dumps(
            asdict(manifest), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
        )
    )


def verify_gate_manifest(
    evidence_root: Path,
    manifest_path: Path,
) -> GateEvidenceManifest:
    """Recompute the manifest and all artifact hashes from disk."""
    try:
        manifest = _read_manifest(manifest_path)
        rebuilt = build_gate_manifest(
            evidence_root,
            manifest.gate,
            tuple(
                evidence_root / artifact.relative_path
                for artifact in manifest.artifacts
            ),
            blockers=manifest.blockers,
        )
    except (OSError, orjson.JSONDecodeError) as exc:
        raise EvidenceManifestError("manifest could not be read") from exc
    for expected, actual in zip(manifest.artifacts, rebuilt.artifacts, strict=True):
        if expected != actual:
            raise EvidenceManifestError(
                f"artifact hash mismatch: {expected.relative_path}"
            )
    if manifest != rebuilt:
        raise EvidenceManifestError("manifest hash or decision mismatch")
    return manifest


def _artifact(root: Path, path: Path) -> EvidenceArtifact:
    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise EvidenceManifestError("artifact is outside evidence root")
    if not resolved.is_file():
        raise EvidenceManifestError("artifact does not exist")
    payload = resolved.read_bytes()
    return EvidenceArtifact(
        relative_path=resolved.relative_to(root).as_posix(),
        sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        size_bytes=len(payload),
    )


def _payload(
    gate: GateName,
    status: GateStatus,
    artifacts: tuple[EvidenceArtifact, ...],
    blockers: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "gate": gate,
        "status": status,
        "artifacts": [asdict(item) for item in artifacts],
        "blockers": list(blockers),
    }


def _digest(payload: object) -> str:
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _read_manifest(path: Path) -> GateEvidenceManifest:
    value = orjson.loads(path.expanduser().resolve(strict=False).read_bytes())
    if not isinstance(value, dict):
        raise EvidenceManifestError("manifest must be an object")
    raw = cast("Mapping[str, object]", value)
    expected = {
        "schema_version",
        "gate",
        "status",
        "artifacts",
        "blockers",
        "manifest_hash",
    }
    if set(raw) != expected or raw["schema_version"] != _SCHEMA_VERSION:
        raise EvidenceManifestError("manifest schema is invalid")
    gate = raw["gate"]
    status = raw["status"]
    blockers = raw["blockers"]
    artifacts = raw["artifacts"]
    manifest_hash = raw["manifest_hash"]
    if gate not in {"Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}:
        raise EvidenceManifestError("manifest gate is invalid")
    if status not in {"passed", "blocked"}:
        raise EvidenceManifestError("manifest status is invalid")
    if not isinstance(blockers, list):
        raise EvidenceManifestError("manifest blockers are invalid")
    blocker_items = cast("list[object]", blockers)
    if not all(isinstance(item, str) for item in blocker_items):
        raise EvidenceManifestError("manifest blockers are invalid")
    if not isinstance(artifacts, list):
        raise EvidenceManifestError("manifest artifacts are invalid")
    artifact_items = cast("list[object]", artifacts)
    if not isinstance(manifest_hash, str):
        raise EvidenceManifestError("manifest hash is invalid")
    return GateEvidenceManifest(
        schema_version=_SCHEMA_VERSION,
        gate=cast("GateName", gate),
        status=cast("GateStatus", status),
        artifacts=tuple(_parse_artifact(item) for item in artifact_items),
        blockers=tuple(cast("list[str]", blockers)),
        manifest_hash=manifest_hash,
    )


def _parse_artifact(value: object) -> EvidenceArtifact:
    if not isinstance(value, dict):
        raise EvidenceManifestError("manifest artifact must be an object")
    raw = cast("Mapping[str, object]", value)
    if set(raw) != {"relative_path", "sha256", "size_bytes"}:
        raise EvidenceManifestError("manifest artifact schema is invalid")
    relative_path = raw["relative_path"]
    sha256 = raw["sha256"]
    size_bytes = raw["size_bytes"]
    if not isinstance(relative_path, str) or not isinstance(sha256, str):
        raise EvidenceManifestError("manifest artifact identity is invalid")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
        raise EvidenceManifestError("manifest artifact size is invalid")
    return EvidenceArtifact(relative_path, sha256, size_bytes)


__all__ = [
    "EvidenceArtifact",
    "EvidenceManifestError",
    "GateEvidenceManifest",
    "GateName",
    "build_gate_manifest",
    "verify_gate_manifest",
    "write_gate_manifest",
]
