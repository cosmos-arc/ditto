"""Generate a deterministic manifest binding one releasable artifact cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

__all__ = [
    "ArtifactRecord",
    "CohortManifest",
    "CohortManifestError",
    "ReleaseCoordinates",
    "artifact_media_type",
    "build_cohort_manifest",
    "main",
    "write_cohort_manifest",
]

_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)"
    + r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    + r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    + r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class CohortManifestError(ValueError):
    """Raised when release evidence is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class ReleaseCoordinates:
    """Identity shared by every independently deployable cohort artifact."""

    product_version: str
    git_sha: str
    api_contract_version: str
    api_contract_sha256: str
    generated_at: str


class ArtifactRecord(TypedDict):
    """Content identity for one cohort artifact."""

    path: str
    sha256: str
    size_bytes: int
    media_type: str


class ReleaseIdentity(TypedDict):
    """Immutable application and API identities."""

    product_version: str
    git_sha: str
    api_contract_version: str
    api_contract_sha256: str


class CohortManifest(TypedDict):
    """Versioned release cohort document."""

    schema: str
    schema_version: int
    generated_at: str
    release: ReleaseIdentity
    backend_artifact: ArtifactRecord
    web_artifact: ArtifactRecord
    artifacts: list[ArtifactRecord]
    cohort_id: str


def build_cohort_manifest(
    *,
    workspace_root: Path,
    artifact_paths: Sequence[Path],
    backend_artifact_path: Path,
    web_artifact_path: Path,
    release: ReleaseCoordinates,
) -> CohortManifest:
    """Build a deterministic manifest or fail when evidence cannot be proven."""
    root = workspace_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise CohortManifestError("workspace root must be a directory")
    if _SEMVER.fullmatch(release.product_version) is None:
        raise CohortManifestError("product version must be valid SemVer")
    _validate_identity("API contract version", release.api_contract_version)
    if _GIT_SHA.fullmatch(release.git_sha) is None:
        raise CohortManifestError("git SHA must be a lowercase 40- or 64-hex digest")
    if re.fullmatch(r"[0-9a-f]{64}", release.api_contract_sha256) is None:
        raise CohortManifestError("API contract SHA256 must be a lowercase hex digest")
    _validate_generated_at(release.generated_at)
    artifacts = _artifact_records(root, artifact_paths)
    if release.api_contract_sha256 not in {item["sha256"] for item in artifacts}:
        raise CohortManifestError("API contract digest is not present in artifacts")

    artifacts_by_path = {item["path"]: item for item in artifacts}
    backend_record = _artifact_record(root, backend_artifact_path)
    web_record = _artifact_record(root, web_artifact_path)
    if backend_record["path"] not in artifacts_by_path:
        raise CohortManifestError("backend artifact is not present in artifacts")
    if web_record["path"] not in artifacts_by_path:
        raise CohortManifestError("Web artifact is not present in artifacts")

    release_identity: ReleaseIdentity = {
        "product_version": release.product_version,
        "git_sha": release.git_sha,
        "api_contract_version": release.api_contract_version,
        "api_contract_sha256": release.api_contract_sha256,
    }
    manifest_without_id: dict[str, object] = {
        "schema": "ditto.release-cohort",
        "schema_version": 1,
        "generated_at": release.generated_at,
        "release": release_identity,
        "backend_artifact": backend_record,
        "web_artifact": web_record,
        "artifacts": artifacts,
    }
    manifest: CohortManifest = {
        "schema": "ditto.release-cohort",
        "schema_version": 1,
        "generated_at": release.generated_at,
        "release": release_identity,
        "backend_artifact": backend_record,
        "web_artifact": web_record,
        "artifacts": artifacts,
        "cohort_id": hashlib.sha256(
            _canonical_bytes_without_id(manifest_without_id)
        ).hexdigest(),
    }
    return manifest


def _artifact_records(
    root: Path, artifact_paths: Sequence[Path]
) -> list[ArtifactRecord]:
    if not artifact_paths:
        raise CohortManifestError("release cohort requires at least one artifact")
    records: list[ArtifactRecord] = []
    seen: set[str] = set()
    for artifact_path in artifact_paths:
        record = _artifact_record(root, artifact_path)
        if record["path"] in seen:
            raise CohortManifestError(f"duplicate artifact: {record['path']}")
        seen.add(record["path"])
        records.append(record)
    return sorted(records, key=lambda item: item["path"])


def write_cohort_manifest(
    output: Path,
    manifest: CohortManifest,
    *,
    artifact_paths: Sequence[Path],
) -> None:
    """Atomically write canonical JSON without overwriting a cohort artifact."""
    destination = output.expanduser().resolve(strict=False)
    artifact_destinations = {
        path.expanduser().resolve(strict=False) for path in artifact_paths
    }
    if destination in artifact_destinations:
        raise CohortManifestError("manifest output cannot overwrite an artifact")
    if output.is_symlink():
        raise CohortManifestError("manifest output cannot be a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(0o644)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _artifact_record(root: Path, artifact_path: Path) -> ArtifactRecord:
    candidate = (
        artifact_path.expanduser()
        if artifact_path.is_absolute()
        else root / artifact_path.expanduser()
    )
    if candidate.is_symlink():
        raise CohortManifestError(f"artifact cannot be a symlink: {artifact_path}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise CohortManifestError(
            f"artifact is unavailable: {artifact_path}"
        ) from error
    if not resolved.is_relative_to(root):
        raise CohortManifestError(f"artifact escapes workspace: {artifact_path}")
    if not resolved.is_file():
        raise CohortManifestError(f"artifact must be a regular file: {artifact_path}")
    _reject_symlink_components(root, candidate)
    relative = resolved.relative_to(root).as_posix()
    media_type = artifact_media_type(relative)
    return {
        "path": relative,
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
        "media_type": media_type,
    }


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError:
        return
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise CohortManifestError(f"artifact path contains a symlink: {candidate}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_media_type(path: str) -> str:
    """Return the platform-independent media type used in cohort evidence."""
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".tar"):
        return "application/x-tar"
    return "application/octet-stream"


def _canonical_bytes_without_id(manifest: dict[str, object]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _validate_identity(label: str, value: str) -> None:
    if _IDENTITY.fullmatch(value) is None:
        raise CohortManifestError(f"{label} is invalid")


def _validate_generated_at(value: str) -> None:
    if not value.endswith("Z"):
        raise CohortManifestError("generated_at must be an explicit UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise CohortManifestError("generated_at must be ISO-8601") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise CohortManifestError("generated_at must be UTC")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--backend-artifact", type=Path, required=True)
    parser.add_argument("--web-artifact", type=Path, required=True)
    parser.add_argument("--product-version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--api-contract-version", required=True)
    parser.add_argument("--api-contract-sha256", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate one fail-closed release cohort manifest."""
    arguments = _parser().parse_args(argv)
    root = arguments.workspace_root.expanduser().resolve(strict=True)
    artifacts = tuple(
        path if path.is_absolute() else root / path for path in arguments.artifact
    )
    backend_artifact = arguments.backend_artifact
    if not backend_artifact.is_absolute():
        backend_artifact = root / backend_artifact
    web_artifact = arguments.web_artifact
    if not web_artifact.is_absolute():
        web_artifact = root / web_artifact
    manifest = build_cohort_manifest(
        workspace_root=root,
        artifact_paths=artifacts,
        backend_artifact_path=backend_artifact,
        web_artifact_path=web_artifact,
        release=ReleaseCoordinates(
            product_version=arguments.product_version,
            git_sha=arguments.git_sha,
            api_contract_version=arguments.api_contract_version,
            api_contract_sha256=arguments.api_contract_sha256,
            generated_at=arguments.generated_at,
        ),
    )
    output = arguments.output
    if not output.is_absolute():
        output = root / output
    if not output.resolve(strict=False).is_relative_to(root):
        raise CohortManifestError("manifest output must remain inside workspace")
    write_cohort_manifest(output, manifest, artifact_paths=artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
