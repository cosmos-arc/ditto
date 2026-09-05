"""Strictly verify an extracted Ditto release cohort without source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import cast

from tooling.release.cohort_manifest import (
    ArtifactRecord,
    CohortManifest,
    artifact_media_type,
)

__all__ = [
    "CohortVerificationError",
    "main",
    "verify_cohort_manifest",
]

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "generated_at",
        "release",
        "backend_artifact",
        "web_artifact",
        "artifacts",
        "cohort_id",
    }
)
_RELEASE_FIELDS = frozenset(
    {
        "product_version",
        "git_sha",
        "api_contract_version",
        "api_contract_sha256",
    }
)
_ARTIFACT_FIELDS = frozenset({"path", "sha256", "size_bytes", "media_type"})
_ASCII_CONTROL_LIMIT = 32
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)\."
    + r"(?:0|[1-9][0-9]*)"
    + r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    + r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    + r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_LOCK_INPUT_PATHS = frozenset(
    {
        "release-inputs/pixi.lock",
        "release-inputs/bun.lock",
    }
)
_OFFLINE_VERIFIER_PATHS = frozenset(
    {
        "release-tools/tooling/__init__.py",
        "release-tools/tooling/release/__init__.py",
        "release-tools/tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_verify.py",
        "release-tools/verify-cohort.py",
    }
)
_SBOM_PATHS = frozenset(
    {
        "ditto-backend.spdx.json",
        "ditto-web.spdx.json",
    }
)
_COMPATIBILITY_POLICY_PATH = (
    "release-inputs/contracts/cohorts/compatibility-policy.json"
)
_COMPATIBILITY_DIGEST_PATH = (
    "release-inputs/contracts/cohorts/compatibility-policy.sha256"
)
_COMPATIBILITY_POLICY_FIELDS = frozenset(
    {
        "api_contract_version",
        "current",
        "previous",
        "schema",
        "schema_version",
    }
)
_WEB_ARTIFACT_SPDX_ID = "SPDXRef-Ditto-Web-Artifact"


class CohortVerificationError(ValueError):
    """Raised when a cohort document or one of its subjects is unverifiable."""


def verify_cohort_manifest(
    *,
    workspace_root: Path,
    manifest_path: Path,
) -> CohortManifest:
    """Verify one canonical cohort solely from files below ``workspace_root``."""
    root = _workspace_root(workspace_root)
    manifest_candidate = (
        manifest_path.expanduser()
        if manifest_path.is_absolute()
        else root / manifest_path.expanduser()
    )
    manifest_payload = _read_contained_regular_file(
        root,
        manifest_candidate,
        label="release manifest",
    )
    document = _load_json_object(manifest_payload)
    if manifest_payload != _canonical_manifest_bytes(document):
        raise CohortVerificationError(
            "release manifest must use canonical sorted JSON with one LF"
        )
    _require_exact_fields(document, _MANIFEST_FIELDS, label="release manifest")
    if document["schema"] != "ditto.release-cohort":
        raise CohortVerificationError("release manifest schema is invalid")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CohortVerificationError("release manifest schema version must be 1")

    supplied_cohort_id = _string(document, "cohort_id", label="release manifest")
    unsigned = {key: value for key, value in document.items() if key != "cohort_id"}
    expected_cohort_id = hashlib.sha256(_canonical_compact_bytes(unsigned)).hexdigest()
    if (
        _SHA256.fullmatch(supplied_cohort_id) is None
        or supplied_cohort_id != expected_cohort_id
    ):
        raise CohortVerificationError("release manifest cohort_id is invalid")

    _validate_generated_at(_string(document, "generated_at", label="release manifest"))
    release = _release_identity(document["release"])
    artifacts = _artifact_list(root, document["artifacts"])
    artifacts_by_path = {record["path"]: record for record in artifacts}

    backend = _artifact_record(
        document["backend_artifact"],
        label="backend artifact",
    )
    web = _artifact_record(document["web_artifact"], label="Web artifact")
    if artifacts_by_path.get(backend["path"]) != backend:
        raise CohortVerificationError(
            "backend artifact record does not match the artifacts list"
        )
    if artifacts_by_path.get(web["path"]) != web:
        raise CohortVerificationError(
            "Web artifact record does not match the artifacts list"
        )

    _verify_bound_release_runtime(
        root=root,
        artifacts_by_path=artifacts_by_path,
        release=release,
        web_artifact=web,
    )

    return cast(CohortManifest, document)


def _verify_bound_release_runtime(
    *,
    root: Path,
    artifacts_by_path: Mapping[str, ArtifactRecord],
    release: Mapping[str, str],
    web_artifact: ArtifactRecord,
) -> None:
    missing_locks = sorted(_LOCK_INPUT_PATHS.difference(artifacts_by_path))
    if missing_locks:
        raise CohortVerificationError(
            f"required release input is missing: {', '.join(missing_locks)}"
        )
    missing_verifier = sorted(_OFFLINE_VERIFIER_PATHS.difference(artifacts_by_path))
    if missing_verifier:
        raise CohortVerificationError(
            "required offline verifier artifact is missing: "
            + ", ".join(missing_verifier)
        )
    contract_path = (
        f"release-inputs/contracts/openapi/{release['api_contract_version']}.json"
    )
    contract_record = artifacts_by_path.get(contract_path)
    if contract_record is None:
        raise CohortVerificationError(
            f"required release input is missing: {contract_path}"
        )
    if contract_record["sha256"] != release["api_contract_sha256"]:
        raise CohortVerificationError(
            "release contract digest does not bind the versioned contract artifact"
        )
    _verify_sbom_evidence(
        root=root,
        artifacts_by_path=artifacts_by_path,
        web_artifact=web_artifact,
    )
    _verify_compatibility_evidence(
        root=root,
        artifacts_by_path=artifacts_by_path,
        release=release,
    )


def _load_evidence_object(payload: bytes, *, label: str) -> dict[str, object]:
    try:
        value = cast(object, json.loads(payload))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CohortVerificationError(f"{label} is not valid JSON") from error
    return _object(value, label=label)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    )


def _verify_sbom_evidence(
    *,
    root: Path,
    artifacts_by_path: Mapping[str, ArtifactRecord],
    web_artifact: ArtifactRecord,
) -> None:
    missing = sorted(_SBOM_PATHS.difference(artifacts_by_path))
    if missing:
        raise CohortVerificationError(
            "required canonical SBOM artifact is missing: " + ", ".join(missing)
        )
    for path in sorted(_SBOM_PATHS):
        label = "Web SBOM" if path == "ditto-web.spdx.json" else "backend SBOM"
        payload = _read_contained_regular_file(root, root / path, label=label)
        document = _load_evidence_object(payload, label=label)
        if payload != _canonical_json_bytes(document):
            raise CohortVerificationError(
                f"{label} must use canonical sorted JSON with one LF"
            )
        spdx_version = document.get("spdxVersion")
        packages = document.get("packages")
        if (
            not isinstance(spdx_version, str)
            or not spdx_version.startswith("SPDX-2.")
            or not isinstance(packages, list)
            or not packages
        ):
            raise CohortVerificationError(
                f"{label} must be a non-empty SPDX 2.x document"
            )
        if path == "ditto-web.spdx.json":
            _verify_web_sbom_subject(document, web_artifact["sha256"])


def _verify_web_sbom_subject(document: Mapping[str, object], web_sha256: str) -> None:
    if document.get("documentDescribes") != [_WEB_ARTIFACT_SPDX_ID]:
        raise CohortVerificationError(
            "Web SBOM documentDescribes must name the Web artifact subject"
        )
    packages = document["packages"]
    if not isinstance(packages, list):
        raise CohortVerificationError("Web SBOM packages must be an array")
    subjects = [
        package
        for package in packages
        if isinstance(package, dict) and package.get("SPDXID") == _WEB_ARTIFACT_SPDX_ID
    ]
    if len(subjects) != 1:
        raise CohortVerificationError(
            "Web SBOM must contain exactly one Web artifact subject"
        )
    if subjects[0].get("checksums") != [
        {"algorithm": "SHA256", "checksumValue": web_sha256}
    ]:
        raise CohortVerificationError(
            "Web SBOM artifact digest does not bind the Web tar"
        )


def _verify_compatibility_policy(
    policy: Mapping[str, object],
    release: Mapping[str, str],
) -> None:
    if policy["schema"] != "ditto.cohort-compatibility-policy":
        raise CohortVerificationError("compatibility policy schema is invalid")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise CohortVerificationError("compatibility policy version must be 1")
    if policy["api_contract_version"] != release["api_contract_version"]:
        raise CohortVerificationError(
            "compatibility policy API contract version does not match release"
        )
    current = _object(policy["current"], label="compatibility current source")
    _require_exact_fields(
        current,
        frozenset({"source"}),
        label="compatibility current source",
    )
    if current["source"] != "web_build":
        raise CohortVerificationError(
            "compatibility policy current source must be web_build"
        )
    previous = policy["previous"]
    if not isinstance(previous, list) or len(previous) > 1:
        raise CohortVerificationError(
            "compatibility policy previous cohorts must contain at most one item"
        )
    for identity in previous:
        validated = _release_identity(identity)
        if validated["api_contract_version"] != release["api_contract_version"]:
            raise CohortVerificationError(
                "compatibility previous cohort uses another API contract version"
            )


def _verify_compatibility_evidence(
    *,
    root: Path,
    artifacts_by_path: Mapping[str, ArtifactRecord],
    release: Mapping[str, str],
) -> None:
    required = {_COMPATIBILITY_POLICY_PATH, _COMPATIBILITY_DIGEST_PATH}
    missing = sorted(required.difference(artifacts_by_path))
    if missing:
        raise CohortVerificationError(
            "required compatibility policy or sidecar is missing: " + ", ".join(missing)
        )
    policy_payload = _read_contained_regular_file(
        root,
        root / _COMPATIBILITY_POLICY_PATH,
        label="compatibility policy",
    )
    digest_payload = _read_contained_regular_file(
        root,
        root / _COMPATIBILITY_DIGEST_PATH,
        label="compatibility policy sidecar",
    )
    policy_sha256 = hashlib.sha256(policy_payload).hexdigest()
    if digest_payload != (f"{policy_sha256}  compatibility-policy.json\n".encode()):
        raise CohortVerificationError(
            "compatibility policy SHA-256 sidecar is malformed or stale"
        )
    policy = _load_evidence_object(policy_payload, label="compatibility policy")
    if policy_payload != _canonical_json_bytes(policy):
        raise CohortVerificationError(
            "compatibility policy must use canonical sorted JSON with one LF"
        )
    _require_exact_fields(
        policy,
        _COMPATIBILITY_POLICY_FIELDS,
        label="compatibility policy",
    )
    _verify_compatibility_policy(policy, release)


def _workspace_root(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise CohortVerificationError("cohort workspace cannot be a symlink")
    try:
        root = candidate.resolve(strict=True)
    except OSError as error:
        raise CohortVerificationError("cohort workspace is unavailable") from error
    if not root.is_dir():
        raise CohortVerificationError("cohort workspace must be a directory")
    return root


def _load_json_object(payload: bytes) -> dict[str, object]:
    try:
        value = cast(
            object,
            json.loads(payload, object_pairs_hook=_unique_json_object),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CohortVerificationError("release manifest is not valid JSON") from error
    return _object(value, label="release manifest")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CohortVerificationError(
                f"release manifest contains duplicate JSON field: {key}"
            )
        result[key] = value
    return result


def _release_identity(value: object) -> dict[str, str]:
    release = _object(value, label="release")
    _require_exact_fields(release, _RELEASE_FIELDS, label="release")
    product_version = _string(release, "product_version", label="release")
    git_sha = _string(release, "git_sha", label="release")
    contract_version = _string(release, "api_contract_version", label="release")
    contract_sha256 = _string(release, "api_contract_sha256", label="release")
    if _SEMVER.fullmatch(product_version) is None:
        raise CohortVerificationError("release product version must be valid SemVer")
    if _GIT_SHA.fullmatch(git_sha) is None:
        raise CohortVerificationError(
            "release Git SHA must be a lowercase 40- or 64-hex digest"
        )
    if _IDENTITY.fullmatch(contract_version) is None:
        raise CohortVerificationError("release API contract version is invalid")
    if _SHA256.fullmatch(contract_sha256) is None:
        raise CohortVerificationError(
            "release API contract SHA-256 must be a lowercase hex digest"
        )
    return {
        "product_version": product_version,
        "git_sha": git_sha,
        "api_contract_version": contract_version,
        "api_contract_sha256": contract_sha256,
    }


def _artifact_list(root: Path, value: object) -> list[ArtifactRecord]:
    if not isinstance(value, list) or not value:
        raise CohortVerificationError("artifacts must be a non-empty JSON array")
    records: list[ArtifactRecord] = []
    for index, item in enumerate(value):
        record = _artifact_record(item, label=f"artifact[{index}]")
        actual_sha256, actual_size = _inspect_artifact(root, record["path"])
        if actual_size != record["size_bytes"]:
            raise CohortVerificationError(
                f"artifact size does not match file: {record['path']}"
            )
        expected_media_type = artifact_media_type(record["path"])
        if record["media_type"] != expected_media_type:
            raise CohortVerificationError(
                f"artifact media type is invalid: {record['path']}"
            )
        if actual_sha256 != record["sha256"]:
            raise CohortVerificationError(
                f"artifact SHA-256 does not match file: {record['path']}"
            )
        records.append(record)

    paths = [record["path"] for record in records]
    if len(paths) != len(set(paths)):
        raise CohortVerificationError("artifacts contain a duplicate path")
    if paths != sorted(paths):
        raise CohortVerificationError("artifacts must be sorted by canonical path")
    return records


def _artifact_record(value: object, *, label: str) -> ArtifactRecord:
    record = _object(value, label=label)
    _require_exact_fields(record, _ARTIFACT_FIELDS, label=label)
    path = _string(record, "path", label=label)
    _validate_relative_path(path)
    sha256 = _string(record, "sha256", label=label)
    if _SHA256.fullmatch(sha256) is None:
        raise CohortVerificationError(f"{label} SHA-256 is invalid")
    size = record["size_bytes"]
    if type(size) is not int or size < 0:
        raise CohortVerificationError(f"{label} size_bytes must be a non-negative int")
    media_type = _string(record, "media_type", label=label)
    if not media_type or any(character.isspace() for character in media_type):
        raise CohortVerificationError(f"{label} media_type is invalid")
    return {
        "path": path,
        "sha256": sha256,
        "size_bytes": size,
        "media_type": media_type,
    }


def _validate_relative_path(value: str) -> PurePosixPath:
    if (
        not value
        or "\\" in value
        or ":" in value
        or any(ord(character) < _ASCII_CONTROL_LIMIT for character in value)
    ):
        raise CohortVerificationError(f"artifact path is not canonical: {value!r}")
    parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise CohortVerificationError(
            f"artifact path must be a contained relative path: {value!r}"
        )
    if path.as_posix() != value:
        raise CohortVerificationError(f"artifact path is not canonical: {value!r}")
    return path


def _inspect_artifact(root: Path, relative_path: str) -> tuple[str, int]:
    portable = _validate_relative_path(relative_path)
    candidate = root.joinpath(*portable.parts)
    descriptor, size = _open_contained_regular_file(
        root,
        candidate,
        label=f"artifact {relative_path}",
    )
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest(), size


def _read_contained_regular_file(root: Path, path: Path, *, label: str) -> bytes:
    descriptor, _ = _open_contained_regular_file(root, path, label=label)
    with os.fdopen(descriptor, "rb") as stream:
        try:
            return stream.read()
        except OSError as error:
            raise CohortVerificationError(f"could not read {label}") from error


def _open_contained_regular_file(
    root: Path,
    path: Path,
    *,
    label: str,
) -> tuple[int, int]:
    candidate = _contained_regular_candidate(root, path, label=label)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise CohortVerificationError(f"could not open {label}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CohortVerificationError(f"{label} must be a regular file")
        return descriptor, metadata.st_size
    except BaseException:
        os.close(descriptor)
        raise


def _contained_regular_candidate(root: Path, path: Path, *, label: str) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        lexical = candidate.absolute().relative_to(root)
    except ValueError as error:
        raise CohortVerificationError(f"{label} escapes cohort workspace") from error
    if any(component in {".", ".."} for component in lexical.parts):
        raise CohortVerificationError(f"{label} escapes cohort workspace")
    current = root
    metadata = root.lstat()
    for component in lexical.parts:
        current /= component
        try:
            metadata = current.lstat()
        except OSError as error:
            raise CohortVerificationError(f"{label} is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise CohortVerificationError(f"{label} cannot contain a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise CohortVerificationError(f"{label} must be a regular file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise CohortVerificationError(f"{label} is unavailable") from error
    if not resolved.is_relative_to(root):
        raise CohortVerificationError(f"{label} escapes cohort workspace")
    return candidate


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CohortVerificationError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _string(raw: Mapping[str, object], field: str, *, label: str) -> str:
    value = raw[field]
    if not isinstance(value, str):
        raise CohortVerificationError(f"{label} {field} must be a string")
    return value


def _require_exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise CohortVerificationError(
            f"{label} fields are invalid: "
            + f"expected={sorted(expected)}, actual={sorted(actual)}"
        )


def _validate_generated_at(value: str) -> None:
    if not value.endswith("Z"):
        raise CohortVerificationError(
            "release manifest generated_at must be an explicit UTC timestamp"
        )
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise CohortVerificationError(
            "release manifest generated_at must be a valid UTC timestamp"
        ) from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise CohortVerificationError(
            "release manifest generated_at must be an explicit UTC timestamp"
        )


def _canonical_manifest_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    )


def _canonical_compact_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("release-cohort.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify a release cohort and print its immutable identity."""
    arguments = _parser().parse_args(argv)
    verified = verify_cohort_manifest(
        workspace_root=arguments.workspace_root,
        manifest_path=arguments.manifest,
    )
    sys.stdout.write(f"cohort-verify: PASS: {verified['cohort_id']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
