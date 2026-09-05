"""Build, inspect, scan, and smoke the two independently deployable artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

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
        release_root / "release-inputs" / "pixi.lock",
        release_root / "release-inputs" / "bun.lock",
    )
    source_inputs = (
        root / "contracts" / "openapi" / "v1.json",
        root / "contracts" / "cohorts" / "compatibility-policy.json",
        root / "contracts" / "cohorts" / "compatibility-policy.sha256",
        root / "pixi.lock",
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
    environment_lock_sha = _sha256(workspace / "pixi.lock")
    web_dist = workspace / "apps" / "web" / "dist"
    _verify_live_runtime_config(web_dist)
    output = workspace / "dist"
    output.mkdir(parents=True, exist_ok=True)
    image = f"ditto-ci:{git_sha[:12]}"
    _run(
        [
            docker,
            "build",
            "--pull",
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
    image_tar = output / "ditto-image.tar"
    web_tar = output / "ditto-web.tar"
    _run(
        [docker, "save", "--output", str(image_tar), image],
        cwd=workspace,
        timeout_seconds=_DOCKER_EXPORT_TIMEOUT_SECONDS,
    )
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
        ],
        timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
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
    _run_ephemeral_container(
        docker,
        workspace,
        purpose="trivy-backend",
        arguments=[
            "--volume",
            f"{output}:/work:ro",
            _TRIVY,
            "image",
            "--input",
            "/work/ditto-image.tar",
            "--exit-code",
            "1",
            "--severity",
            "HIGH,CRITICAL",
        ],
        timeout_seconds=_SCANNER_TIMEOUT_SECONDS,
    )
    _smoke_container(docker, workspace, image, release=release)

    manifest_path, cohort_artifacts = _materialize_portable_cohort(
        workspace=workspace,
        output=output,
        artifact_paths=(
            image_tar,
            web_tar,
            output / "ditto-backend.spdx.json",
            output / "ditto-web.spdx.json",
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
    """Run the root-local artifact gate."""
    root = Path(__file__).resolve().parents[2]
    try:
        run_artifact_gate(root)
    except (ArtifactGateError, OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"artifact-gate: FAIL: {error}\n")
        return 1
    sys.stdout.write("artifact-gate: PASS\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
