"""Build, inspect, scan, and smoke the two independently deployable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from tooling.release.cohort_bundle import (
    create_release_bundle,
    stage_offline_verifier,
)
from tooling.release.cohort_manifest import (
    ReleaseCoordinates,
    build_cohort_manifest,
    write_cohort_manifest,
)
from tooling.release.cohort_verify import verify_cohort_manifest
from tooling.release.environment_identity import environment_identity

_SYFT = (
    "ghcr.io/anchore/syft:v1.51.1@sha256:"
    "95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c"
)
_TRIVY = (
    "ghcr.io/aquasecurity/trivy:0.74.0@sha256:"
    "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
_GIT_SHA_LENGTH = 40
_HTTP_OK = 200
_OFFLINE_READINESS_VALUE = "ci-smoke-offline-credential"
_DOCKER_PROBE_TIMEOUT_SECONDS = 30
_GIT_TIMEOUT_SECONDS = 30
_DOCKER_BUILD_TIMEOUT_SECONDS = 30 * 60
_DOCKER_EXPORT_TIMEOUT_SECONDS = 10 * 60
_SCANNER_TIMEOUT_SECONDS = 20 * 60
_DOCKER_CONTROL_TIMEOUT_SECONDS = 60
_WEB_METADATA_MAX_BYTES = 64 * 1024
_WEB_METADATA_FILENAME = "ditto-build-metadata.json"
_WEB_ARTIFACT_SPDX_ID = "SPDXRef-Ditto-Web-Artifact"
_BACKEND_LIBRARY_STAGES = ("runtime-libraries", "debian-libraries")
_SOURCE_PROVENANCE_FILENAME = "ditto-backend-source-provenance.spdx.json"


class ArtifactGateError(RuntimeError):
    """Raised when an artifact cannot be built or independently verified."""


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ArtifactGateError(f"required executable is unavailable: {name}")
    return executable


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    capture_output: bool = False,
    expected: frozenset[int] = frozenset({0}),
) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            check=False,
            capture_output=capture_output,
            text=capture_output,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise ArtifactGateError(
            f"artifact command timed out after {timeout_seconds}s: "
            + shlex.join(command)
        ) from error
    if result.returncode not in expected:
        details = result.stderr.strip() if capture_output else ""
        raise ArtifactGateError(
            f"artifact command failed ({result.returncode}): {shlex.join(command)}"
            + (f"\n{details}" if details else "")
        )
    return result.stdout.strip() if capture_output else ""


def _container_name(root: Path, purpose: str) -> str:
    workspace_digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return f"ditto-{purpose}-{workspace_digest}"


def _remove_container(docker: str, root: Path, name: str) -> None:
    try:
        _run(
            [docker, "rm", "--force", name],
            cwd=root,
            capture_output=True,
            timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
        )
    except ArtifactGateError as error:
        if "No such container" not in str(error):
            raise


def _run_ephemeral_container(
    docker: str,
    root: Path,
    *,
    purpose: str,
    arguments: Sequence[str],
    timeout_seconds: int,
) -> None:
    name = _container_name(root, purpose)
    _remove_container(docker, root, name)
    primary_error: BaseException | None = None
    with tempfile.TemporaryDirectory(prefix=f"{name}-") as temporary:
        cidfile = Path(temporary) / "container.cid"
        try:
            _run(
                [
                    docker,
                    "run",
                    "--name",
                    name,
                    "--cidfile",
                    str(cidfile),
                    *arguments,
                ],
                cwd=root,
                timeout_seconds=timeout_seconds,
            )
        except BaseException as error:
            primary_error = error
            raise
        finally:
            _cleanup_after_container(
                docker,
                root,
                name,
                primary_error=primary_error,
            )


def _docker_user_arguments() -> list[str]:
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        return []
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def _syft_sandbox_arguments() -> list[str]:
    """Keep offline scans unprivileged with disposable extraction/cache space."""
    return [
        "--network",
        "none",
        *_docker_user_arguments(),
        "--tmpfs",
        "/scratch:rw,nosuid,nodev,mode=1777",
        "--env",
        "TMPDIR=/scratch",
        "--env",
        "HOME=/scratch",
        "--env",
        "XDG_CACHE_HOME=/scratch/.cache",
        "--env",
        "SYFT_CHECK_FOR_APP_UPDATE=false",
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_release_input(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ArtifactGateError(f"release input cannot be a symlink: {source}")
    try:
        resolved_source = source.resolve(strict=True)
    except OSError as error:
        raise ArtifactGateError(f"release input is unavailable: {source}") from error
    if not resolved_source.is_file():
        raise ArtifactGateError(f"release input must be a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = destination.parent
    while current != current.parent:
        if current.is_symlink():
            raise ArtifactGateError(
                f"release input destination cannot contain a symlink: {destination}"
            )
        current = current.parent
    if destination.is_symlink():
        raise ArtifactGateError(
            f"release input destination cannot be a symlink: {destination}"
        )
    shutil.copyfile(resolved_source, destination)


def _materialize_portable_cohort(
    *,
    workspace: Path,
    output: Path,
    artifact_paths: Sequence[Path],
    backend_artifact: Path,
    web_artifact: Path,
    release: ReleaseCoordinates,
) -> tuple[Path, tuple[Path, ...]]:
    """Stage immutable inputs, write the cohort, and verify it from ``output``."""
    root = workspace.expanduser().resolve(strict=True)
    if output.is_symlink():
        raise ArtifactGateError("release output cannot be a symlink")
    release_root = output.expanduser().resolve(strict=True)
    if not release_root.is_relative_to(root):
        raise ArtifactGateError("release output must remain inside workspace")

    staged_inputs = (
        release_root / "release-inputs" / "contracts" / "openapi" / "v1.json",
        release_root
        / "release-inputs"
        / "contracts"
        / "cohorts"
        / "compatibility-policy.json",
        release_root
        / "release-inputs"
        / "contracts"
        / "cohorts"
        / "compatibility-policy.sha256",
        release_root / "release-inputs" / "uv.lock",
        release_root / "release-inputs" / ".python-version",
        release_root / "release-inputs" / "Dockerfile",
        release_root / "release-inputs" / "bun.lock",
    )
    source_inputs = (
        root / "contracts" / "openapi" / "v1.json",
        root / "contracts" / "cohorts" / "compatibility-policy.json",
        root / "contracts" / "cohorts" / "compatibility-policy.sha256",
        root / "uv.lock",
        root / ".python-version",
        root / "deploy/docker/Dockerfile",
        root / "bun.lock",
    )
    for source, destination in zip(source_inputs, staged_inputs, strict=True):
        _copy_release_input(source, destination)

    verifier_files = stage_offline_verifier(
        source_root=root,
        workspace_root=release_root,
    )
    cohort_artifacts = tuple(artifact_paths) + staged_inputs + verifier_files
    manifest = build_cohort_manifest(
        workspace_root=release_root,
        artifact_paths=cohort_artifacts,
        backend_artifact_path=backend_artifact,
        web_artifact_path=web_artifact,
        release=release,
    )
    manifest_path = release_root / "release-cohort.json"
    write_cohort_manifest(
        manifest_path,
        manifest,
        artifact_paths=cohort_artifacts,
    )
    verify_cohort_manifest(
        workspace_root=release_root,
        manifest_path=manifest_path,
    )
    return manifest_path, cohort_artifacts


def _release_identity(root: Path) -> tuple[str, str, str]:
    git = _executable("git")
    dirty = _run(
        [git, "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if dirty:
        raise ArtifactGateError(
            "release source tree is dirty; commit or remove tracked/untracked changes"
        )
    workspace = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if not isinstance(workspace, dict) or not isinstance(workspace.get("version"), str):
        raise ArtifactGateError("root package.json must declare a string version")
    git_sha = _run(
        [git, "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if len(git_sha) != _GIT_SHA_LENGTH or any(
        character not in "0123456789abcdef" for character in git_sha
    ):
        raise ArtifactGateError("Git HEAD is not a full lowercase SHA-1")
    contract_sha = _sha256(root / "contracts" / "openapi" / "v1.json")
    return workspace["version"], git_sha, contract_sha


def _normalized_web_tar(web_dist: Path, output: Path, *, timestamp: int) -> None:
    if not web_dist.is_dir():
        raise ArtifactGateError("Web production build is unavailable")

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = timestamp
        return info

    with tarfile.open(output, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(web_dist.rglob("*")):
            archive.add(
                path,
                arcname=path.relative_to(web_dist).as_posix(),
                recursive=False,
                filter=normalize,
            )


def _json_object(payload: bytes, *, label: str) -> dict[str, object]:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ArtifactGateError(f"{label} contains duplicate field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ArtifactGateError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ArtifactGateError(f"{label} must be a JSON object")
    return value


def _expected_web_identity(release: ReleaseCoordinates) -> dict[str, str]:
    return {
        "apiContractSha256": release.api_contract_sha256,
        "apiContractVersion": release.api_contract_version,
        "gitSha": release.git_sha,
        "productVersion": release.product_version,
    }


def _verify_web_artifact_metadata(
    web_tar: Path,
    *,
    release: ReleaseCoordinates,
) -> None:
    try:
        with tarfile.open(web_tar, mode="r:") as archive:
            matches = [
                member
                for member in archive.getmembers()
                if member.name == _WEB_METADATA_FILENAME
            ]
            if len(matches) != 1:
                qualifier = "missing" if not matches else "duplicate"
                raise ArtifactGateError(
                    f"Web artifact build metadata is {qualifier}: "
                    + _WEB_METADATA_FILENAME
                )
            member = matches[0]
            if not member.isfile() or member.size > _WEB_METADATA_MAX_BYTES:
                raise ArtifactGateError(
                    "Web artifact build metadata must be a bounded regular file"
                )
            stream = archive.extractfile(member)
            if stream is None:
                raise ArtifactGateError("Web artifact build metadata is unreadable")
            payload = stream.read(_WEB_METADATA_MAX_BYTES + 1)
    except (OSError, tarfile.TarError) as error:
        raise ArtifactGateError("Web artifact tar is unreadable") from error

    document = _json_object(payload, label="Web artifact build metadata")
    required_fields = {
        "apiContractSha256",
        "apiContractVersion",
        "gitSha",
        "productVersion",
        "schema",
        "schemaVersion",
    }
    optional_fields = {"compatibilityPolicy"}
    actual_fields = set(document)
    if not required_fields.issubset(actual_fields) or not actual_fields.issubset(
        required_fields | optional_fields
    ):
        raise ArtifactGateError("Web artifact build metadata fields are invalid")
    if document["schema"] != "ditto.web-build-metadata":
        raise ArtifactGateError("Web artifact build metadata schema is invalid")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise ArtifactGateError("Web artifact build metadata schema version is invalid")
    for field, expected in _expected_web_identity(release).items():
        if document[field] != expected:
            raise ArtifactGateError(
                f"Web artifact build metadata {field} does not match release identity"
            )


def _stage_web_dependency_metadata(workspace: Path, destination: Path) -> None:
    for relative in ("package.json", "apps/web/package.json", "bun.lock"):
        _copy_release_input(workspace / relative, destination / relative)


def _canonicalize_spdx_sbom(sbom_path: Path, *, label: str) -> None:
    document = _json_object(sbom_path.read_bytes(), label=label)
    spdx_version = document.get("spdxVersion")
    packages = document.get("packages")
    if (
        not isinstance(spdx_version, str)
        or not spdx_version.startswith("SPDX-2.")
        or not isinstance(packages, list)
        or not packages
    ):
        raise ArtifactGateError(f"{label} must be a non-empty SPDX 2.x document")
    sbom_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _web_package_metadata(package_manifest: Path) -> tuple[str, str, set[str]]:
    manifest = _json_object(
        package_manifest.read_bytes(),
        label="Web package manifest",
    )
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        raise ArtifactGateError("Web package manifest dependencies must be non-empty")
    direct_dependencies = {
        name
        for name, constraint in dependencies.items()
        if isinstance(name, str) and name and isinstance(constraint, str) and constraint
    }
    if direct_dependencies != set(dependencies):
        raise ArtifactGateError("Web package manifest direct dependencies are invalid")
    package_name = manifest.get("name")
    package_version = manifest.get("version")
    if not isinstance(package_name, str) or not package_name:
        raise ArtifactGateError("Web package manifest name must be non-empty")
    if not isinstance(package_version, str) or not package_version:
        raise ArtifactGateError("Web package manifest version must be non-empty")
    return package_name, package_version, direct_dependencies


def _web_dependency_ids(
    packages: list[object], direct_dependencies: set[str]
) -> dict[str, str]:
    dependency_ids: dict[str, str] = {}
    existing_ids: set[str] = set()
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            raise ArtifactGateError(f"Web SBOM package[{index}] must be an object")
        name = package.get("name")
        spdx_id = package.get("SPDXID")
        if not isinstance(name, str) or not isinstance(spdx_id, str):
            raise ArtifactGateError(
                f"Web SBOM package[{index}] requires name and SPDXID"
            )
        if spdx_id in existing_ids:
            raise ArtifactGateError(f"Web SBOM contains duplicate SPDXID: {spdx_id}")
        existing_ids.add(spdx_id)
        if name in direct_dependencies and name not in dependency_ids:
            dependency_ids[name] = spdx_id
    missing = sorted(direct_dependencies.difference(dependency_ids))
    if missing:
        raise ArtifactGateError(
            "Web SBOM is missing direct runtime dependencies: " + ", ".join(missing)
        )
    if _WEB_ARTIFACT_SPDX_ID in existing_ids:
        raise ArtifactGateError("Web SBOM already contains reserved artifact SPDXID")
    return dependency_ids


def _web_artifact_package(
    *, web_tar: Path, package_name: str, package_version: str
) -> dict[str, object]:
    return {
        "SPDXID": _WEB_ARTIFACT_SPDX_ID,
        "checksums": [
            {
                "algorithm": "SHA256",
                "checksumValue": _sha256(web_tar),
            }
        ],
        "copyrightText": "NOASSERTION",
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "name": f"{package_name}-artifact",
        "versionInfo": package_version,
    }


def _bind_and_verify_web_sbom(
    sbom_path: Path,
    *,
    web_tar: Path,
    package_manifest: Path,
) -> None:
    document = _json_object(
        sbom_path.read_bytes(),
        label="Web SPDX SBOM",
    )
    spdx_version = document.get("spdxVersion")
    if not isinstance(spdx_version, str) or not spdx_version.startswith("SPDX-2."):
        raise ArtifactGateError("Web SBOM must be an SPDX 2.x JSON document")
    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ArtifactGateError("Web SBOM packages must be non-empty")
    package_name, package_version, direct_dependencies = _web_package_metadata(
        package_manifest
    )
    dependency_ids = _web_dependency_ids(packages, direct_dependencies)
    packages.append(
        _web_artifact_package(
            web_tar=web_tar,
            package_name=package_name,
            package_version=package_version,
        )
    )
    document["documentDescribes"] = [_WEB_ARTIFACT_SPDX_ID]
    relationships = document.get("relationships")
    if relationships is None:
        relationships = []
        document["relationships"] = relationships
    if not isinstance(relationships, list):
        raise ArtifactGateError("Web SBOM relationships must be an array")
    relationships.extend(
        {
            "relatedSpdxElement": dependency_ids[name],
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": _WEB_ARTIFACT_SPDX_ID,
        }
        for name in sorted(dependency_ids)
    )
    sbom_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _verify_live_runtime_config(web_dist: Path) -> None:
    raw = json.loads(
        (web_dist / "ditto-runtime-config.json").read_text(encoding="utf-8")
    )
    if raw != {
        "schemaVersion": 1,
        "runtime": "live",
        "apiOrigin": "http://127.0.0.1:8000",
    }:
        raise ArtifactGateError(
            "Web release runtime config is not the safe live default"
        )


def _start_smoke_container(
    docker: str,
    root: Path,
    *,
    name: str,
    cidfile: Path,
    image: str,
) -> None:
    container_id = _run(
        [
            docker,
            "run",
            "--detach",
            "--name",
            name,
            "--cidfile",
            str(cidfile),
            "--env",
            f"TUSHARE_TOKEN={_OFFLINE_READINESS_VALUE}",
            "--publish",
            "127.0.0.1::8000",
            image,
        ],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
    )
    if not cidfile.is_file():
        raise ArtifactGateError("container runtime did not materialize cidfile")
    recorded_id = cidfile.read_text(encoding="utf-8").strip()
    if not recorded_id or recorded_id != container_id:
        raise ArtifactGateError("container stdout and cidfile identity disagree")


def _published_smoke_port(docker: str, root: Path, name: str) -> int:
    mapping = _run(
        [docker, "port", name, "8000/tcp"],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
    )
    try:
        return int(mapping.rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError) as error:
        raise ArtifactGateError(
            f"container published an invalid port mapping: {mapping!r}"
        ) from error


def _wait_for_container_readiness(
    docker: str,
    root: Path,
    *,
    name: str,
    port: int,
) -> None:
    deadline = time.monotonic() + 60
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/readyz",
                timeout=2,
            ) as response:
                if response.status == _HTTP_OK:
                    return
        except (OSError, urllib.error.URLError) as error:
            last_error = error
        time.sleep(1)
    logs = _run(
        [docker, "logs", name],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
    )
    raise ArtifactGateError(
        f"container readiness timed out: {last_error}; logs={logs[-2000:]}"
    )


def _verify_container_release_identity(
    *,
    port: int,
    release: ReleaseCoordinates,
) -> None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/status",
            timeout=5,
        ) as response:
            if response.status != _HTTP_OK:
                raise ArtifactGateError(
                    "container status endpoint did not return HTTP 200"
                )
            status_payload = response.read()
    except (OSError, urllib.error.URLError) as error:
        raise ArtifactGateError("container status identity request failed") from error
    status = _json_object(status_payload, label="container status response")
    expected_status = {
        "product_version": release.product_version,
        "git_sha": release.git_sha,
        "api_contract_version": release.api_contract_version,
        "api_contract_sha256": release.api_contract_sha256,
    }
    for field, expected in expected_status.items():
        if status.get(field) != expected:
            raise ArtifactGateError(
                f"container status {field} does not match release identity"
            )


def _cleanup_after_container(
    docker: str,
    root: Path,
    name: str,
    *,
    primary_error: BaseException | None,
) -> None:
    try:
        _remove_container(docker, root, name)
    except ArtifactGateError as cleanup_error:
        if primary_error is None:
            raise
        primary_error.add_note(f"container cleanup also failed: {cleanup_error}")


def _smoke_container(
    docker: str,
    root: Path,
    image: str,
    *,
    release: ReleaseCoordinates,
) -> None:
    configured_user = _run(
        [docker, "image", "inspect", "--format", "{{.Config.User}}", image],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_PROBE_TIMEOUT_SECONDS,
    )
    if configured_user != "65532:65532":
        raise ArtifactGateError(f"container user is not non-root: {configured_user!r}")

    name = _container_name(root, "backend-smoke")
    _remove_container(docker, root, name)
    primary_error: BaseException | None = None
    with tempfile.TemporaryDirectory(prefix=f"{name}-") as temporary:
        cidfile = Path(temporary) / "container.cid"
        try:
            _start_smoke_container(
                docker,
                root,
                name=name,
                cidfile=cidfile,
                image=image,
            )
            port = _published_smoke_port(docker, root, name)
            _wait_for_container_readiness(
                docker,
                root,
                name=name,
                port=port,
            )
            _verify_container_release_identity(port=port, release=release)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            _cleanup_after_container(
                docker,
                root,
                name,
                primary_error=primary_error,
            )


def _archive_image_config(path: Path) -> str:
    """Resolve Docker's exported config digest (distinct from OCI index IDs)."""
    with tarfile.open(path) as archive:
        manifest_file = archive.extractfile("manifest.json")
        if manifest_file is None:
            raise ArtifactGateError("image archive has no manifest")
        manifests = json.load(manifest_file)
        if (
            not isinstance(manifests, list)
            or len(manifests) != 1
            or not isinstance(manifests[0], dict)
        ):
            raise ArtifactGateError("image archive must contain one image subject")
        config = manifests[0].get("Config")
        if not isinstance(config, str):
            raise ArtifactGateError("image archive has no config subject")
        config_file = archive.extractfile(config)
        if config_file is None:
            raise ArtifactGateError("image archive config is not a file")
        return "sha256:" + hashlib.sha256(config_file.read()).hexdigest()


def _docker_export_filesystem(
    docker: str,
    root: Path,
    *,
    image: str,
    destination: Path,
    platform: str,
) -> None:
    container_id = _run(
        [docker, "create", "--platform", platform, image],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
    )
    try:
        _run(
            [docker, "export", "--output", str(destination), container_id],
            cwd=root,
            timeout_seconds=_DOCKER_EXPORT_TIMEOUT_SECONDS,
        )
    finally:
        _remove_container(docker, root, container_id)


def _verify_scanner_subject(path: Path, *, image: str, scanner: str) -> None:
    report = _json_object(path.read_bytes(), label=f"{scanner} report")
    source = report.get("source") if scanner == "syft" else report
    metadata = (
        source.get("metadata" if scanner == "syft" else "Metadata")
        if isinstance(source, dict)
        else None
    )
    actual = (
        metadata.get("imageID" if scanner == "syft" else "ImageID")
        if isinstance(metadata, dict)
        else None
    )
    if actual != image:
        raise ArtifactGateError(
            f"{scanner} subject does not match build output: {actual!r} != {image}"
        )
    sys.stdout.write(f"{scanner} subject verified: {image}\n")


def _backend_library_sources(root: Path) -> tuple[tuple[str, str], ...]:
    content = (root / "deploy" / "docker" / "Dockerfile").read_text(encoding="utf-8")
    sources: dict[str, str] = {}
    for image, stage in re.findall(r"^FROM (\S+) AS (\S+)$", content, re.MULTILINE):
        if stage in _BACKEND_LIBRARY_STAGES:
            sources[stage] = image
    if tuple(sources) != _BACKEND_LIBRARY_STAGES:
        raise ArtifactGateError("backend copied-library source stages are incomplete")
    return tuple(sources.items())


def _source_results(report: dict[str, object]) -> list[dict[str, object]]:
    results = report.get("Results")
    if not isinstance(results, list) or not all(
        isinstance(result, dict) for result in results
    ):
        raise ArtifactGateError("trivy source report has malformed results")
    return results


def _source_packages(report: dict[str, object]) -> dict[str, dict[str, object]]:
    packages: dict[str, dict[str, object]] = {}
    for result in _source_results(report):
        inventory = result.get("Packages")
        if inventory is None:
            continue
        if not isinstance(inventory, list) or not all(
            isinstance(package, dict) for package in inventory
        ):
            raise ArtifactGateError("trivy source report has malformed packages")
        for package in inventory:
            name = package.get("Name")
            if not isinstance(name, str) or not name:
                raise ArtifactGateError("trivy source report has a malformed package")
            packages[name] = package
    return packages


def _vulnerable_installed_files(
    report: dict[str, object],
) -> dict[str, tuple[str, ...]]:
    vulnerable: set[str] = set()
    for result in _source_results(report):
        vulnerabilities = result.get("Vulnerabilities")
        if vulnerabilities is None:
            continue
        if not isinstance(vulnerabilities, list) or not all(
            isinstance(vulnerability, dict) for vulnerability in vulnerabilities
        ):
            raise ArtifactGateError("trivy source report has malformed vulnerabilities")
        for vulnerability in vulnerabilities:
            package_name = vulnerability.get("PkgName")
            if not isinstance(package_name, str) or not package_name:
                raise ArtifactGateError("trivy source report has a malformed package")
            vulnerable.add(package_name)
    packages = _source_packages(report)
    missing = sorted(vulnerable.difference(packages))
    if missing:
        raise ArtifactGateError(
            "trivy source report lacks inventory for vulnerable packages: "
            + ", ".join(missing)
        )
    installed: dict[str, tuple[str, ...]] = {}
    for name in sorted(vulnerable):
        files = packages[name].get("InstalledFiles")
        if not isinstance(files, list) or not files:
            raise ArtifactGateError(
                f"trivy source report lacks installed files for {name}"
            )
        paths = tuple(path for path in files if isinstance(path, str))
        if len(paths) != len(files) or any(
            not path.startswith("/") or ".." in PurePosixPath(path).parts
            for path in paths
        ):
            raise ArtifactGateError(
                f"trivy source report has invalid installed files for {name}"
            )
        installed[name] = paths
    return installed


def _tar_member_index(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    return {member.name.removeprefix("./"): member for member in archive.getmembers()}


def _resolved_tar_member(
    index: Mapping[str, tarfile.TarInfo],
    path: str,
) -> tarfile.TarInfo | None:
    current = path.removeprefix("/")
    for _ in range(16):
        member = index.get(current)
        if member is None:
            return None
        if member.issym():
            target = member.linkname
            if not target.startswith("/"):
                target = posixpath.normpath(
                    posixpath.join(posixpath.dirname(current), target)
                )
            current = target.removeprefix("/")
            continue
        if member.islnk():
            current = member.linkname.removeprefix("/")
            continue
        return member
    raise ArtifactGateError(f"container filesystem has a symlink cycle: {path}")


def _tar_file_digest(
    archive: tarfile.TarFile,
    index: Mapping[str, tarfile.TarInfo],
    path: str,
) -> str | None:
    member = _resolved_tar_member(index, path)
    if member is None or member.isdir():
        return None
    stream = archive.extractfile(member)
    if stream is None:
        raise ArtifactGateError(f"container filesystem file is unreadable: {path}")
    return hashlib.sha256(stream.read()).hexdigest()


def _verify_vulnerable_source_files(
    report: dict[str, object],
    *,
    source_export: Path,
    final_export: Path,
) -> None:
    vulnerable_files = _vulnerable_installed_files(report)
    unchanged: list[str] = []
    try:
        with tarfile.open(source_export) as source, tarfile.open(final_export) as final:
            source_index = _tar_member_index(source)
            final_index = _tar_member_index(final)
            for package, paths in vulnerable_files.items():
                for path in paths:
                    source_digest = _tar_file_digest(source, source_index, path)
                    if source_digest is None:
                        raise ArtifactGateError(
                            "trivy source installed file is absent from source export: "
                            + path
                        )
                    final_digest = _tar_file_digest(final, final_index, path)
                    if final_digest == source_digest:
                        unchanged.append(f"{package}:{path}")
    except tarfile.TarError as error:
        raise ArtifactGateError(
            "backend source/final container export is unreadable"
        ) from error
    if unchanged:
        raise ArtifactGateError(
            "vulnerable source files remain byte-identical in final image: "
            + ", ".join(unchanged[:5])
        )


def _verify_scanner_source(
    path: Path,
    *,
    source: str,
    stage: str,
    image_id: str | None = None,
) -> None:
    del stage
    report = _json_object(path.read_bytes(), label="trivy source report")
    metadata = report.get("Metadata")
    if not isinstance(metadata, dict):
        raise ArtifactGateError("trivy source report has malformed metadata")
    digests = metadata.get("RepoDigests")
    if isinstance(digests, list) and source in digests:
        return
    scanned_image = metadata.get("ImageID")
    if image_id is None or scanned_image != image_id:
        raise ArtifactGateError(
            f"trivy source does not match pinned image: {digests!r}/"
            + f"{scanned_image!r} != {source!r}/{image_id!r}"
        )


def _spdx_id(value: str) -> str:
    return "SPDXRef-" + re.sub(r"[^A-Za-z0-9.-]+", "-", value)


def _write_backend_source_provenance(
    reports: Sequence[Path],
    sources: Sequence[tuple[str, str]],
    output: Path,
) -> Path:
    packages: list[dict[str, object]] = []
    relationships: list[dict[str, object]] = []
    described: list[str] = []
    for (stage, source), report_path in zip(sources, reports, strict=True):
        report = _json_object(report_path.read_bytes(), label="trivy source report")
        digest = source.rsplit("@", 1)[-1].removeprefix("sha256:")
        image_id = _spdx_id(f"backend-source-image-{stage}")
        described.append(image_id)
        packages.append(
            {
                "SPDXID": image_id,
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
                "copyrightText": "NOASSERTION",
                "downloadLocation": source,
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": source,
                "sourceInfo": f"Pinned copied-library source for stage {stage}",
                "versionInfo": digest,
            }
        )
        for index, package in enumerate(_source_packages(report).values()):
            package_id = _spdx_id(f"backend-source-{stage}-{index}")
            version = package.get("Version")
            identifier = package.get("Identifier")
            purl = identifier.get("PURL") if isinstance(identifier, dict) else None
            entry: dict[str, object] = {
                "SPDXID": package_id,
                "copyrightText": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": package["Name"],
                "sourceInfo": f"Inventory from pinned source image {source}",
            }
            if isinstance(version, str) and version:
                entry["versionInfo"] = version
            if isinstance(purl, str) and purl:
                entry["externalRefs"] = [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": purl,
                    }
                ]
            packages.append(entry)
            relationships.append(
                {
                    "spdxElementId": package_id,
                    "relatedSpdxElement": image_id,
                    "relationshipType": "CONTAINED_BY",
                }
            )
    document = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": "1970-01-01T00:00:00Z",
            "creators": ["Tool: ditto-artifact-gate"],
        },
        "dataLicense": "CC0-1.0",
        "documentDescribes": described,
        "documentNamespace": "https://ditto.invalid/spdx/backend-source-provenance",
        "name": "ditto-backend-source-provenance",
        "packages": packages,
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }
    destination = output / _SOURCE_PROVENANCE_FILENAME
    destination.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _bind_backend_source_provenance(sbom_path: Path, provenance_path: Path) -> None:
    sbom = _json_object(sbom_path.read_bytes(), label="backend SPDX SBOM")
    provenance = _json_object(
        provenance_path.read_bytes(), label="backend source provenance SPDX"
    )
    described = sbom.get("documentDescribes")
    if (
        not isinstance(described, list)
        or len(described) != 1
        or not isinstance(described[0], str)
        or not described[0]
    ):
        raise ArtifactGateError("backend SPDX SBOM must describe one subject")
    references = sbom.setdefault("externalDocumentRefs", [])
    if not isinstance(references, list):
        raise ArtifactGateError("backend SPDX external document refs must be an array")
    relationships = sbom.setdefault("relationships", [])
    if not isinstance(relationships, list):
        raise ArtifactGateError("backend SPDX relationships must be an array")
    source_images = provenance.get("documentDescribes")
    if not isinstance(source_images, list):
        raise ArtifactGateError("backend source provenance must describe source images")
    for value in source_images:
        if not isinstance(value, str):
            raise ArtifactGateError("backend source provenance image ID is invalid")
        stage = value.removeprefix("SPDXRef-backend-source-image-")
        document_id = f"DocumentRef-{stage}"
        references.append(
            {
                "checksum": {
                    "algorithm": "SHA256",
                    "checksumValue": _sha256(provenance_path),
                },
                "externalDocumentId": document_id,
                "spdxDocument": provenance["documentNamespace"],
            }
        )
        relationships.append(
            {
                "relatedSpdxElement": f"{document_id}:{value}",
                "relationshipType": "DEPENDS_ON",
                "spdxElementId": described[0],
            }
        )
    sbom_path.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _tar_json(archive: tarfile.TarFile, name: str) -> object:
    stream = archive.extractfile(name)
    if stream is None:
        raise ArtifactGateError(f"source archive JSON is absent: {name}")
    return json.load(stream)


def _required_blob_name(digest: object) -> str:
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise ArtifactGateError("source archive digest is invalid")
    return "blobs/sha256/" + digest.removeprefix("sha256:")


def _oci_amd64_descriptor(archive: tarfile.TarFile) -> dict[str, object] | None:
    if archive.extractfile("index.json") is None:
        return None
    index = _tar_json(archive, "index.json")
    descriptors = index.get("manifests") if isinstance(index, dict) else None
    if not isinstance(descriptors, list) or len(descriptors) != 1:
        raise ArtifactGateError("source archive index is malformed")
    root = _tar_json(archive, _required_blob_name(descriptors[0].get("digest")))
    children = root.get("manifests") if isinstance(root, dict) else None
    if not isinstance(children, list):
        raise ArtifactGateError("source archive manifest list is malformed")
    amd64 = [
        child
        for child in children
        if isinstance(child, dict)
        and child.get("platform") == {"architecture": "amd64", "os": "linux"}
    ]
    if len(amd64) != 1:
        raise ArtifactGateError("source archive lacks one linux/amd64 image")
    return amd64[0]


def _legacy_amd64_image_id(archive: tarfile.TarFile) -> str:
    manifests = _tar_json(archive, "manifest.json")
    if not isinstance(manifests, list) or not manifests:
        raise ArtifactGateError("source archive manifest is malformed")
    for image in manifests:
        if not isinstance(image, dict) or not isinstance(image.get("Config"), str):
            raise ArtifactGateError("source archive config is malformed")
        config_name = image["Config"]
        config_stream = archive.extractfile(config_name)
        if config_stream is None:
            raise ArtifactGateError("source archive config is absent")
        payload = config_stream.read()
        config = json.loads(payload)
        if config.get("architecture") == "amd64" and config.get("os") == "linux":
            return "sha256:" + hashlib.sha256(payload).hexdigest()
    raise ArtifactGateError("source archive lacks a linux/amd64 image")


def _write_amd64_docker_archive(
    source: tarfile.TarFile,
    target: tarfile.TarFile,
    descriptor: dict[str, object],
) -> str:
    child = _tar_json(source, _required_blob_name(descriptor.get("digest")))
    config = child.get("config") if isinstance(child, dict) else None
    layers = child.get("layers") if isinstance(child, dict) else None
    if not isinstance(config, dict) or not isinstance(layers, list):
        raise ArtifactGateError("source archive image manifest is malformed")
    config_name = _required_blob_name(config.get("digest"))
    layer_names = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ArtifactGateError("source archive layer is malformed")
        layer_names.append(_required_blob_name(layer.get("digest")))
    docker_manifest = [{"Config": config_name, "Layers": layer_names, "RepoTags": None}]
    payload = json.dumps(docker_manifest, separators=(",", ":")).encode()
    member = tarfile.TarInfo("manifest.json")
    member.size = len(payload)
    members = {original.name: original for original in source.getmembers()}
    for name in sorted({config_name, *layer_names}):
        original = members.get(name)
        if original is None:
            raise ArtifactGateError(f"source archive blob is absent: {name}")
        stream = source.extractfile(original)
        if stream is None:
            raise ArtifactGateError(f"source archive blob is unreadable: {name}")
        target.addfile(original, stream)
    target.addfile(member, io.BytesIO(payload))
    return "sha256:" + config_name.removeprefix("blobs/sha256/")


def _select_amd64_archive(archive: Path) -> str:
    """Return the linux/amd64 config ID and make that image the only archive subject."""
    selected = archive.with_suffix(".amd64.tar")
    try:
        with tarfile.open(archive) as source:
            descriptor = _oci_amd64_descriptor(source)
            if descriptor is None:
                return _legacy_amd64_image_id(source)
            with tarfile.open(selected, "w") as target:
                image_id = _write_amd64_docker_archive(source, target, descriptor)
    except (OSError, tarfile.TarError, json.JSONDecodeError) as error:
        raise ArtifactGateError("source archive is unreadable") from error
    archive.unlink()
    selected.replace(archive)
    return image_id


def _scan_source_archive(
    docker: str,
    root: Path,
    *,
    source: str,
    archive: Path,
    output: Path,
    report: Path,
) -> None:
    _run(
        [docker, "pull", "--platform", "linux/amd64", source],
        cwd=root,
        timeout_seconds=_DOCKER_EXPORT_TIMEOUT_SECONDS,
    )
    repo_digests = _run(
        [docker, "image", "inspect", "--format", '{{join .RepoDigests ","}}', source],
        cwd=root,
        capture_output=True,
        timeout_seconds=_DOCKER_CONTROL_TIMEOUT_SECONDS,
    ).split(",")
    if source not in repo_digests:
        raise ArtifactGateError(
            f"docker source does not match pinned image: {repo_digests!r}"
        )
    _run(
        [docker, "save", "--output", str(archive), source],
        cwd=root,
        timeout_seconds=_DOCKER_EXPORT_TIMEOUT_SECONDS,
    )
    image_id = _select_amd64_archive(archive)
    _run_ephemeral_container(
        docker,
        root,
        purpose="trivy-source",
        arguments=[
            "--volume",
            "ditto-trivy-cache:/root/.cache/trivy",
            "--volume",
            f"{archive.parent}:/source:ro",
            "--volume",
            f"{output}:/work",
            _TRIVY,
            "image",
            "--platform",
            "linux/amd64",
            "--input",
            f"/source/{archive.name}",
            "--format",
            "json",
            "--output",
            f"/work/{report.name}",
            "--exit-code",
            "0",
            "--severity",
            "HIGH,CRITICAL",
            "--scanners",
            "vuln",
            "--list-all-pkgs",
        ],
        timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
    )
    _verify_scanner_source(report, source=source, stage="", image_id=image_id)


def scan_backend_library_sources(
    root: Path,
    output: Path,
    *,
    final_image: str | None = None,
) -> tuple[tuple[Path, ...], Path]:
    """Scan copied-library sources and reject vulnerable files in the final image."""
    root = root.expanduser().resolve(strict=True)
    output = output.expanduser().resolve(strict=True)
    docker = _executable("docker")
    sources = _backend_library_sources(root)
    reports: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="ditto-backend-source-") as temporary:
        scratch = Path(temporary)
        for stage, source in sources:
            report = output / f"trivy-backend-source-{stage}.json"
            archive = scratch / f"{stage}.tar"
            _scan_source_archive(
                docker,
                root,
                source=source,
                archive=archive,
                output=output,
                report=report,
            )
            reports.append(report)
        if final_image is not None:
            final_export = scratch / "final.tar"
            _docker_export_filesystem(
                docker,
                root,
                image=final_image,
                destination=final_export,
                platform="linux/amd64",
            )
            for (_stage, source), report in zip(sources, reports, strict=True):
                source_export = scratch / "source-filesystem.tar"
                _docker_export_filesystem(
                    docker,
                    root,
                    image=source,
                    destination=source_export,
                    platform="linux/amd64",
                )
                document = _json_object(
                    report.read_bytes(), label="trivy source report"
                )
                _verify_vulnerable_source_files(
                    document,
                    source_export=source_export,
                    final_export=final_export,
                )
    provenance = _write_backend_source_provenance(reports, sources, output)
    return tuple(reports), provenance


def _scan_backend_library_sources(
    docker: str,
    root: Path,
    output: Path,
) -> tuple[tuple[Path, ...], Path]:
    del docker
    return scan_backend_library_sources(root, output)


def run_artifact_gate(root: Path) -> None:
    """Build both artifacts, generate SBOMs, scan the image, and prove readiness."""
    workspace = root.expanduser().resolve(strict=True)
    docker = _executable("docker")
    _run(
        [docker, "version", "--format", "{{.Server.Version}}"],
        cwd=workspace,
        timeout_seconds=_DOCKER_PROBE_TIMEOUT_SECONDS,
    )
    version, git_sha, contract_sha = _release_identity(workspace)
    environment_lock_sha = environment_identity(workspace)
    web_dist = workspace / "apps" / "web" / "dist"
    _verify_live_runtime_config(web_dist)
    output = workspace / "dist"
    output.mkdir(parents=True, exist_ok=True)
    image = f"ditto-ci:{git_sha[:12]}"
    image_id_file = output / "image-id.txt"
    image_id_file.unlink(missing_ok=True)
    _run(
        [
            docker,
            "build",
            "--platform",
            "linux/amd64",
            "--pull",
            "--iidfile",
            str(image_id_file),
            "--file",
            "deploy/docker/Dockerfile",
            "--tag",
            image,
            "--build-arg",
            f"DITTO_PRODUCT_VERSION={version}",
            "--build-arg",
            f"DITTO_GIT_SHA={git_sha}",
            "--build-arg",
            f"DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH={environment_lock_sha}",
            "--build-arg",
            "DITTO_API_CONTRACT_VERSION=v1",
            "--build-arg",
            f"DITTO_API_CONTRACT_SHA256={contract_sha}",
            ".",
        ],
        cwd=workspace,
        timeout_seconds=_DOCKER_BUILD_TIMEOUT_SECONDS,
    )
    image = image_id_file.read_text(encoding="utf-8").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("Docker build did not produce an immutable image ID")
    sys.stdout.write(f"Artifact subject: {image}\n")
    sys.stdout.flush()
    image_tar = output / "ditto-image.tar"
    web_tar = output / "ditto-web.tar"
    _run(
        [docker, "save", "--output", str(image_tar), image],
        cwd=workspace,
        timeout_seconds=_DOCKER_EXPORT_TIMEOUT_SECONDS,
    )
    config_digest = _archive_image_config(image_tar)
    sys.stdout.write(f"Exported config subject: {config_digest}\n")
    git = _executable("git")
    commit_timestamp = int(
        _run(
            [git, "show", "-s", "--format=%ct", git_sha],
            cwd=workspace,
            capture_output=True,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
        )
    )
    release = ReleaseCoordinates(
        product_version=version,
        git_sha=git_sha,
        api_contract_version="v1",
        api_contract_sha256=contract_sha,
        generated_at=datetime.fromtimestamp(
            commit_timestamp,
            UTC,
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _normalized_web_tar(web_dist, web_tar, timestamp=commit_timestamp)
    _verify_web_artifact_metadata(web_tar, release=release)

    _run_ephemeral_container(
        docker,
        workspace,
        purpose="syft-backend",
        arguments=[
            *_syft_sandbox_arguments(),
            "--volume",
            f"{output}:/work",
            _SYFT,
            "docker-archive:/work/ditto-image.tar",
            "--output",
            "spdx-json=/work/ditto-backend.spdx.json",
            "--output",
            "syft-json=/work/ditto-backend.syft.json",
        ],
        timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
    )
    _verify_scanner_subject(
        output / "ditto-backend.syft.json", image=config_digest, scanner="syft"
    )
    _canonicalize_spdx_sbom(
        output / "ditto-backend.spdx.json",
        label="backend SPDX SBOM",
    )
    with tempfile.TemporaryDirectory(prefix="ditto-web-sbom-") as temporary:
        sbom_source = Path(temporary).resolve(strict=True)
        _stage_web_dependency_metadata(workspace, sbom_source)
        _run_ephemeral_container(
            docker,
            workspace,
            purpose="syft-web",
            arguments=[
                *_syft_sandbox_arguments(),
                "--volume",
                f"{sbom_source}:/web-source:ro",
                "--volume",
                f"{output}:/work",
                _SYFT,
                "dir:/web-source",
                "--output",
                "spdx-json=/work/ditto-web.spdx.json",
            ],
            timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
        )
    _bind_and_verify_web_sbom(
        output / "ditto-web.spdx.json",
        web_tar=web_tar,
        package_manifest=workspace / "apps" / "web" / "package.json",
    )
    _smoke_container(docker, workspace, image, release=release)
    _run_ephemeral_container(
        docker,
        workspace,
        purpose="trivy-backend",
        arguments=[
            "--volume",
            "ditto-trivy-cache:/root/.cache/trivy",
            "--volume",
            f"{output}:/work",
            _TRIVY,
            "image",
            "--input",
            "/work/ditto-image.tar",
            "--format",
            "json",
            "--output",
            "/work/trivy-backend.json",
            "--exit-code",
            "1",
            "--severity",
            "HIGH,CRITICAL",
        ],
        timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
    )
    _verify_scanner_subject(
        output / "trivy-backend.json", image=config_digest, scanner="trivy"
    )
    source_reports, source_provenance = scan_backend_library_sources(
        workspace, output, final_image=image
    )
    _bind_backend_source_provenance(
        output / "ditto-backend.spdx.json", source_provenance
    )
    _canonicalize_spdx_sbom(
        output / "ditto-backend.spdx.json",
        label="backend SPDX SBOM",
    )

    manifest_path, cohort_artifacts = _materialize_portable_cohort(
        workspace=workspace,
        output=output,
        artifact_paths=(
            image_tar,
            web_tar,
            output / "ditto-backend.spdx.json",
            source_provenance,
            output / "ditto-web.spdx.json",
            *source_reports,
        ),
        backend_artifact=image_tar,
        web_artifact=web_tar,
        release=release,
    )
    bundle_path = create_release_bundle(
        workspace_root=output,
        manifest_path=manifest_path,
        output_path=output / "ditto-release-cohort.tar",
        source_date_epoch=commit_timestamp,
    )
    evidence = {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in (*cohort_artifacts, manifest_path, bundle_path)
    }
    (output / "CI-SHA256SUMS.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Run the root-local artifact gate or a focused release subprocess."""
    parser = argparse.ArgumentParser(prog="tooling.release.artifact-gate")
    commands = parser.add_subparsers(dest="command")
    scanner = commands.add_parser(
        "scan-backend-sources",
        help="scan copied-library sources and bind them to the final image",
    )
    scanner.add_argument("--output", type=Path, required=True)
    scanner.add_argument("--final-image")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    try:
        if args.command == "scan-backend-sources":
            reports, provenance = scan_backend_library_sources(
                root,
                args.output,
                final_image=args.final_image,
            )
            sys.stdout.write(
                "backend source provenance verified: "
                + ", ".join(path.name for path in (*reports, provenance))
                + "\n"
            )
        else:
            run_artifact_gate(root)
    except (
        ArtifactGateError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        sys.stderr.write(f"artifact-gate: FAIL: {error}\n")
        return 1
    sys.stdout.write("artifact-gate: PASS\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
