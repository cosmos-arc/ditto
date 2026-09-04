"""Build, inspect, scan, and smoke the two independently deployable artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

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
    capture_output: bool = False,
) -> str:
    result = subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        check=False,
        capture_output=capture_output,
        text=capture_output,
    )
    if result.returncode != 0:
        details = result.stderr.strip() if capture_output else ""
        raise ArtifactGateError(
            f"artifact command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{details}" if details else "")
        )
    return result.stdout.strip() if capture_output else ""


def _docker_user_arguments() -> list[str]:
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        return []
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _release_identity(root: Path) -> tuple[str, str, str]:
    workspace = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if not isinstance(workspace, dict) or not isinstance(workspace.get("version"), str):
        raise ArtifactGateError("root package.json must declare a string version")
    git = _executable("git")
    git_sha = _run(
        [git, "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
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


def _smoke_container(docker: str, root: Path, image: str) -> None:
    configured_user = _run(
        [docker, "image", "inspect", "--format", "{{.Config.User}}", image],
        cwd=root,
        capture_output=True,
    )
    if configured_user != "65532:65532":
        raise ArtifactGateError(f"container user is not non-root: {configured_user!r}")

    container_id = _run(
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--env",
            f"TUSHARE_TOKEN={_OFFLINE_READINESS_VALUE}",
            "--publish",
            "127.0.0.1::8000",
            image,
        ],
        cwd=root,
        capture_output=True,
    )
    try:
        mapping = _run(
            [docker, "port", container_id, "8000/tcp"],
            cwd=root,
            capture_output=True,
        )
        port = int(mapping.rsplit(":", maxsplit=1)[1])
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
            [docker, "logs", container_id],
            cwd=root,
            capture_output=True,
        )
        raise ArtifactGateError(
            f"container readiness timed out: {last_error}; logs={logs[-2000:]}"
        )
    finally:
        subprocess.run(  # noqa: S603
            [docker, "stop", container_id],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def run_artifact_gate(root: Path) -> None:
    """Build both artifacts, generate SBOMs, scan the image, and prove readiness."""
    workspace = root.expanduser().resolve(strict=True)
    docker = _executable("docker")
    _run(
        [docker, "version", "--format", "{{.Server.Version}}"],
        cwd=workspace,
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
    )
    image_tar = output / "ditto-image.tar"
    web_tar = output / "ditto-web.tar"
    _run([docker, "save", "--output", str(image_tar), image], cwd=workspace)
    git = _executable("git")
    commit_timestamp = int(
        _run(
            [git, "show", "-s", "--format=%ct", git_sha],
            cwd=workspace,
            capture_output=True,
        )
    )
    _normalized_web_tar(web_dist, web_tar, timestamp=commit_timestamp)

    user = _docker_user_arguments()
    _run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            *user,
            "--volume",
            f"{output}:/work",
            _SYFT,
            "docker-archive:/work/ditto-image.tar",
            "--output",
            "spdx-json=/work/ditto-backend.spdx.json",
        ],
        cwd=workspace,
    )
    _run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            *user,
            "--volume",
            f"{web_dist}:/web:ro",
            "--volume",
            f"{output}:/work",
            _SYFT,
            "dir:/web",
            "--output",
            "spdx-json=/work/ditto-web.spdx.json",
        ],
        cwd=workspace,
    )
    _run(
        [
            docker,
            "run",
            "--rm",
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
        cwd=workspace,
    )
    _smoke_container(docker, workspace, image)

    evidence = {
        path.name: _sha256(path)
        for path in (
            image_tar,
            web_tar,
            output / "ditto-backend.spdx.json",
            output / "ditto-web.spdx.json",
        )
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
