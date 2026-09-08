"""Focused tests for release artifact container smoke policy."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import NoReturn

import pytest

from tooling.release import artifact_gate
from tooling.release.cohort_manifest import CohortManifest, ReleaseCoordinates
from tooling.release.cohort_verify import verify_cohort_manifest
from tooling.release.tests.image_fixture import write_image

ROOT = Path(__file__).resolve().parents[3]


def test_owned_temporary_directory_resolves_system_symlink_before_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    alias = tmp_path / "system-temp-alias"
    alias.symlink_to(scratch, target_is_directory=True)

    class Temporary:
        def __enter__(self) -> str:
            return str(alias)

        def __exit__(self, *_args: object) -> None:
            return None

    class StagingObserved(Exception):
        pass

    def stage(_workspace: Path, destination: Path) -> NoReturn:
        assert destination == scratch.resolve(strict=True)
        raise StagingObserved

    def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(artifact_gate, "_executable", str)
    monkeypatch.setattr(
        artifact_gate, "_release_identity", lambda _root: ("1.0.0", "a" * 40, "b" * 64)
    )
    monkeypatch.setattr(artifact_gate, "_sha256", lambda _path: "c" * 64)
    monkeypatch.setattr(artifact_gate, "environment_identity", lambda _root: "c" * 64)
    monkeypatch.setattr(
        artifact_gate, "_archive_image_config", lambda _path: "sha256:" + "d" * 64
    )

    def run(command: list[str], **_kwargs: object) -> str:
        if command[1] == "build":
            Path(command[command.index("--iidfile") + 1]).write_text(
                "sha256:" + "d" * 64
            )
        return "0"

    monkeypatch.setattr(artifact_gate, "_run", run)
    for name in (
        "_verify_live_runtime_config",
        "_normalized_web_tar",
        "_verify_web_artifact_metadata",
        "_run_ephemeral_container",
        "_canonicalize_spdx_sbom",
        "_verify_scanner_subject",
        "_scan_backend_library_sources",
    ):
        monkeypatch.setattr(artifact_gate, name, noop)
    monkeypatch.setattr(
        artifact_gate.tempfile, "TemporaryDirectory", lambda **_kwargs: Temporary()
    )
    monkeypatch.setattr(artifact_gate, "_stage_web_dependency_metadata", stage)
    with pytest.raises(StagingObserved):
        artifact_gate.run_artifact_gate(tmp_path)


def test_syft_has_writable_ephemeral_storage_without_root_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifact_gate, "_docker_user_arguments", lambda: ["--user", "501:20"]
    )
    assert artifact_gate._syft_sandbox_arguments() == [
        "--network",
        "none",
        "--user",
        "501:20",
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


class _HealthyResponse:
    status = 200

    def __init__(self, payload: bytes = b"") -> None:
        self._payload = payload

    def __enter__(self) -> _HealthyResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _release() -> ReleaseCoordinates:
    return ReleaseCoordinates(
        product_version="1.2.3",
        git_sha="a" * 40,
        api_contract_version="v1",
        api_contract_sha256="b" * 64,
        generated_at="2026-09-05T00:00:00Z",
    )


def test_artifact_command_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def timeout_run(command: list[str], **_kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired(command, timeout=17)

    monkeypatch.setattr(artifact_gate.subprocess, "run", timeout_run)

    with pytest.raises(artifact_gate.ArtifactGateError, match=r"timed out.*17"):
        artifact_gate._run(
            ["docker", "version"],
            cwd=tmp_path,
            timeout_seconds=17,
        )


def test_container_smoke_injects_offline_token_only_at_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Artifact smoke must not expect a credential-free image to be ready."""
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool = False,
        timeout_seconds: int,
        expected: frozenset[int] = frozenset({0}),
    ) -> str:
        del capture_output, expected
        commands.append(command)
        if command[1:3] == ["image", "inspect"]:
            return "65532:65532"
        if command[1] == "run":
            cidfile = Path(command[command.index("--cidfile") + 1])
            cidfile.write_text("container-id\n", encoding="utf-8")
            return "container-id"
        if command[1] == "port":
            return "127.0.0.1:18000"
        if command[1] in {"logs", "rm"}:
            return ""
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(artifact_gate, "_run", fake_run)
    monkeypatch.setattr(
        artifact_gate.urllib.request,
        "urlopen",
        lambda url, **_kwargs: (
            _HealthyResponse(
                json.dumps(
                    {
                        "product_version": "1.2.3",
                        "git_sha": "a" * 40,
                        "api_contract_version": "v1",
                        "api_contract_sha256": "b" * 64,
                    }
                ).encode()
            )
            if str(url).endswith("/api/v1/status")
            else _HealthyResponse()
        ),
    )

    artifact_gate._smoke_container(
        "docker",
        tmp_path,
        "ditto-ci:test",
        release=_release(),
    )

    docker_run = next(command for command in commands if command[1] == "run")
    assert "TUSHARE_TOKEN=ci-smoke-offline-credential" in docker_run
    assert docker_run.index("--env") < docker_run.index("ditto-ci:test")
    assert "--name" in docker_run
    assert "--cidfile" in docker_run
    assert any(command[1:3] == ["rm", "--force"] for command in commands)


def test_container_smoke_rejects_runtime_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool = False,
        timeout_seconds: int,
        expected: frozenset[int] = frozenset({0}),
    ) -> str:
        del cwd, capture_output, timeout_seconds, expected
        if command[1:3] == ["image", "inspect"]:
            return "65532:65532"
        if command[1] == "run":
            cidfile = Path(command[command.index("--cidfile") + 1])
            cidfile.write_text("container-id\n", encoding="utf-8")
            return "container-id"
        if command[1] == "port":
            return "127.0.0.1:18000"
        if command[1] in {"logs", "rm"}:
            return ""
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(artifact_gate, "_run", fake_run)
    monkeypatch.setattr(
        artifact_gate.urllib.request,
        "urlopen",
        lambda url, **_kwargs: (
            _HealthyResponse(
                json.dumps(
                    {
                        "product_version": "9.9.9",
                        "git_sha": "a" * 40,
                        "api_contract_version": "v1",
                        "api_contract_sha256": "b" * 64,
                    }
                ).encode()
            )
            if str(url).endswith("/api/v1/status")
            else _HealthyResponse()
        ),
    )

    with pytest.raises(artifact_gate.ArtifactGateError, match="product_version"):
        artifact_gate._smoke_container(
            "docker",
            tmp_path,
            "ditto-ci:test",
            release=_release(),
        )


def test_web_artifact_metadata_is_read_from_the_final_tar(
    tmp_path: Path,
) -> None:
    web_dist = tmp_path / "web"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<main>Ditto</main>\n", encoding="utf-8")
    (web_dist / "ditto-build-metadata.json").write_text(
        json.dumps(
            {
                "apiContractSha256": "b" * 64,
                "apiContractVersion": "v1",
                "gitSha": "a" * 40,
                "productVersion": "1.2.3",
                "schema": "ditto.web-build-metadata",
                "schemaVersion": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    web_tar = tmp_path / "ditto-web.tar"
    artifact_gate._normalized_web_tar(web_dist, web_tar, timestamp=1)

    artifact_gate._verify_web_artifact_metadata(web_tar, release=_release())

    with tarfile.open(web_tar, mode="a:") as archive:
        replacement = tmp_path / "replacement.json"
        replacement.write_text(
            '{"productVersion":"9.9.9"}\n',
            encoding="utf-8",
        )
        archive.add(replacement, arcname="ditto-build-metadata.json")
    with pytest.raises(artifact_gate.ArtifactGateError, match=r"metadata.*duplicate"):
        artifact_gate._verify_web_artifact_metadata(web_tar, release=_release())


def test_web_sbom_binds_tar_and_contains_every_direct_runtime_dependency(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps(
            {
                "name": "@ditto/web",
                "version": "1.2.3",
                "dependencies": {"react": "19.2.4", "zustand": "5.0.12"},
            }
        ),
        encoding="utf-8",
    )
    web_tar = tmp_path / "ditto-web.tar"
    web_tar.write_bytes(b"web artifact")
    sbom = tmp_path / "ditto-web.spdx.json"
    sbom.write_text(
        json.dumps(
            {
                "SPDXID": "SPDXRef-DOCUMENT",
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {"SPDXID": "SPDXRef-Package-react", "name": "react"},
                    {"SPDXID": "SPDXRef-Package-zustand", "name": "zustand"},
                ],
                "relationships": [],
            }
        ),
        encoding="utf-8",
    )

    artifact_gate._bind_and_verify_web_sbom(
        sbom,
        web_tar=web_tar,
        package_manifest=package,
    )

    document = json.loads(sbom.read_text(encoding="utf-8"))
    artifact = next(
        item
        for item in document["packages"]
        if item["SPDXID"] == "SPDXRef-Ditto-Web-Artifact"
    )
    assert artifact["checksums"] == [
        {
            "algorithm": "SHA256",
            "checksumValue": hashlib.sha256(web_tar.read_bytes()).hexdigest(),
        }
    ]
    assert document["documentDescribes"] == ["SPDXRef-Ditto-Web-Artifact"]


def test_web_sbom_rejects_a_missing_direct_runtime_dependency(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        '{"name":"@ditto/web","version":"1.2.3","dependencies":{"react":"19.2.4","zustand":"5.0.12"}}',
        encoding="utf-8",
    )
    web_tar = tmp_path / "ditto-web.tar"
    web_tar.write_bytes(b"web artifact")
    sbom = tmp_path / "ditto-web.spdx.json"
    sbom.write_text(
        '{"SPDXID":"SPDXRef-DOCUMENT","spdxVersion":"SPDX-2.3","packages":[{"SPDXID":"SPDXRef-Package-react","name":"react"}],"relationships":[]}',
        encoding="utf-8",
    )

    with pytest.raises(artifact_gate.ArtifactGateError, match=r"direct.*zustand"):
        artifact_gate._bind_and_verify_web_sbom(
            sbom,
            web_tar=web_tar,
            package_manifest=package,
        )


def test_local_artifact_gate_materializes_and_verifies_a_portable_cohort(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = tmp_path / "contracts" / "openapi" / "v1.json"
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b'{"openapi":"3.1.0"}\n')
    (tmp_path / "uv.lock").write_bytes(b"uv\n")
    (tmp_path / ".python-version").write_text("cpython-3.13.14")
    (tmp_path / "deploy/docker").mkdir(parents=True)
    (tmp_path / "deploy/docker/Dockerfile").write_text("FROM fixture")
    (tmp_path / "bun.lock").write_bytes(b"bun\n")
    output = tmp_path / "dist"
    output.mkdir()
    backend = output / "ditto-image.tar"
    web = output / "ditto-web.tar"
    backend_sbom = output / "ditto-backend.spdx.json"
    web_sbom = output / "ditto-web.spdx.json"
    write_image(backend, tmp_path, staged=False)
    web.write_bytes(b"web")
    backend_sbom.write_text(
        json.dumps(
            {
                "SPDXID": "SPDXRef-DOCUMENT",
                "packages": [{"SPDXID": "SPDXRef-Backend", "name": "ditto-backend"}],
                "spdxVersion": "SPDX-2.3",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    web_sbom.write_text(
        json.dumps(
            {
                "SPDXID": "SPDXRef-DOCUMENT",
                "documentDescribes": ["SPDXRef-Ditto-Web-Artifact"],
                "packages": [
                    {
                        "SPDXID": "SPDXRef-Ditto-Web-Artifact",
                        "checksums": [
                            {
                                "algorithm": "SHA256",
                                "checksumValue": hashlib.sha256(
                                    web.read_bytes()
                                ).hexdigest(),
                            }
                        ],
                        "name": "@ditto/web-artifact",
                    }
                ],
                "spdxVersion": "SPDX-2.3",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    policy = tmp_path / "contracts" / "cohorts" / "compatibility-policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(
        json.dumps(
            {
                "api_contract_version": "v1",
                "current": {"source": "web_build"},
                "previous": [],
                "schema": "ditto.cohort-compatibility-policy",
                "schema_version": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (policy.parent / "compatibility-policy.sha256").write_text(
        f"{hashlib.sha256(policy.read_bytes()).hexdigest()}"
        "  compatibility-policy.json\n",
        encoding="utf-8",
    )
    for relative in (
        "tooling/__init__.py",
        "tooling/release/__init__.py",
        "tooling/release/cohort_manifest.py",
        "tooling/release/cohort_verify.py",
        "tooling/release/environment_identity.py",
        "tooling/release/offline_verify.py",
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    verification_calls: list[tuple[Path, Path]] = []

    def record_verification(
        *, workspace_root: Path, manifest_path: Path
    ) -> CohortManifest:
        verification_calls.append((workspace_root, manifest_path))
        return verify_cohort_manifest(
            workspace_root=workspace_root,
            manifest_path=manifest_path,
        )

    monkeypatch.setattr(
        artifact_gate,
        "verify_cohort_manifest",
        record_verification,
    )

    manifest_path, cohort_artifacts = artifact_gate._materialize_portable_cohort(
        workspace=tmp_path,
        output=output,
        artifact_paths=(backend, backend_sbom, web, web_sbom),
        backend_artifact=backend,
        web_artifact=web,
        release=ReleaseCoordinates(
            product_version="1.2.3",
            git_sha="a" * 40,
            api_contract_version="v1",
            api_contract_sha256=hashlib.sha256(contract.read_bytes()).hexdigest(),
            generated_at="2026-09-05T00:00:00Z",
        ),
    )

    verified = verify_cohort_manifest(
        workspace_root=output,
        manifest_path=manifest_path,
    )
    paths = {str(record["path"]) for record in verified["artifacts"]}
    assert paths >= {
        "release-inputs/contracts/openapi/v1.json",
        "release-inputs/uv.lock",
        "release-inputs/bun.lock",
        "release-tools/tooling/__init__.py",
        "release-tools/tooling/release/__init__.py",
        "release-tools/tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_verify.py",
        "release-tools/tooling/release/environment_identity.py",
        "release-tools/verify-cohort.py",
    }
    assert all(path.is_relative_to(output) for path in cohort_artifacts)
    assert json.loads(manifest_path.read_text())["cohort_id"] == verified["cohort_id"]
    assert verification_calls == [(output.resolve(), manifest_path)]


def test_release_identity_rejects_tracked_and_untracked_dirty_source(
    tmp_path: Path,
) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q"], cwd=tmp_path, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [git, "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "config", "user.name", "Test"], cwd=tmp_path, check=True
    )
    contract = tmp_path / "contracts" / "openapi" / "v1.json"
    contract.parent.mkdir(parents=True)
    contract.write_text("{}\n")
    (tmp_path / "package.json").write_text('{"version":"1.2.3"}\n')
    (tmp_path / ".gitignore").write_text("ignored-output\n")
    subprocess.run([git, "add", "."], cwd=tmp_path, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [git, "commit", "-qm", "fixture"], cwd=tmp_path, check=True
    )
    (tmp_path / "ignored-output").write_text("ignored\n")

    version, git_sha, _ = artifact_gate._release_identity(tmp_path)

    assert version == "1.2.3"
    assert len(git_sha) == 40
    (tmp_path / "untracked.txt").write_text("untracked\n")
    with pytest.raises(artifact_gate.ArtifactGateError, match="dirty"):
        artifact_gate._release_identity(tmp_path)
    (tmp_path / "untracked.txt").unlink()
    contract.write_text('{"changed":true}\n')
    with pytest.raises(artifact_gate.ArtifactGateError, match="dirty"):
        artifact_gate._release_identity(tmp_path)
    subprocess.run([git, "add", str(contract)], cwd=tmp_path, check=True)  # noqa: S603
    with pytest.raises(artifact_gate.ArtifactGateError, match="dirty"):
        artifact_gate._release_identity(tmp_path)


def test_build_export_and_smoke_use_the_build_output_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mutable tag must not be resolved again by export or readiness checks."""
    commands: list[list[str]] = []
    image_id = "sha256:" + "d" * 64

    def run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        if command[1] == "build":
            assert "--iidfile" in command
            Path(command[command.index("--iidfile") + 1]).write_text(image_id)
        return "0"

    def noop(*_args: object, **_kwargs: object) -> None:
        return None

    class SmokeObserved(Exception):
        pass

    def smoke(_docker: str, _root: Path, image: str, **_kwargs: object) -> None:
        assert image == image_id
        assert (
            next(command for command in commands if command[1] == "save")[-1]
            == image_id
        )
        assert sum(command[1] == "build" for command in commands) == 1
        raise SmokeObserved

    monkeypatch.setattr(artifact_gate, "_executable", str)
    monkeypatch.setattr(
        artifact_gate, "_release_identity", lambda _root: ("1.0.0", "a" * 40, "b" * 64)
    )
    monkeypatch.setattr(artifact_gate, "_sha256", lambda _path: "c" * 64)
    monkeypatch.setattr(artifact_gate, "environment_identity", lambda _root: "c" * 64)
    monkeypatch.setattr(
        artifact_gate, "_archive_image_config", lambda _path: "sha256:" + "d" * 64
    )
    monkeypatch.setattr(artifact_gate, "_run", run)
    for name in (
        "_verify_live_runtime_config",
        "_normalized_web_tar",
        "_verify_web_artifact_metadata",
        "_run_ephemeral_container",
        "_canonicalize_spdx_sbom",
        "_verify_scanner_subject",
        "_scan_backend_library_sources",
        "_stage_web_dependency_metadata",
        "_bind_and_verify_web_sbom",
    ):
        monkeypatch.setattr(artifact_gate, name, noop)
    monkeypatch.setattr(artifact_gate, "_smoke_container", smoke)
    with pytest.raises(SmokeObserved):
        artifact_gate.run_artifact_gate(tmp_path)


def test_backend_library_sources_are_bound_to_release_dockerfile() -> None:
    assert artifact_gate._backend_library_sources(ROOT) == (
        (
            "runtime-libraries",
            "cgr.dev/chainguard/python@sha256:c23539f80289046e2fa734d3f3fc418833fc22d064a50cc43fa9a6edc28c1615",
        ),
        (
            "debian-libraries",
            "gcr.io/distroless/python3-debian13@sha256:f3d5ddc6c64a019fe520e7f005f2880be21e6afc461b10a3c15ef2e4edc71e33",
        ),
    )


def test_scanner_source_mismatch_cannot_pass(tmp_path: Path) -> None:
    report = tmp_path / "source.json"
    report.write_text(json.dumps({"Metadata": {"RepoDigests": ["wrong@sha256:x"]}}))
    with pytest.raises(artifact_gate.ArtifactGateError, match="source"):
        artifact_gate._verify_scanner_source(
            report, source="right@sha256:" + "a" * 64, stage="runtime-libraries"
        )


def test_backend_source_scan_keeps_raw_inventory_for_post_scan_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = "source@sha256:" + "a" * 64

    def sources(_root: Path) -> tuple[tuple[str, str], ...]:
        return (("runtime-libraries", source),)

    def scan_archive(
        _docker: str,
        _root: Path,
        *,
        source: str,
        archive: Path,
        output: Path,
        report: Path,
    ) -> None:
        del source, archive, output
        report.write_text(
            json.dumps(
                {
                    "Metadata": {"ImageID": "sha256:" + "b" * 64},
                    "Results": [{"Packages": [], "Vulnerabilities": None}],
                }
            )
        )

    monkeypatch.setattr(artifact_gate, "_backend_library_sources", sources)
    monkeypatch.setattr(artifact_gate, "_scan_source_archive", scan_archive)

    reports, provenance = artifact_gate.scan_backend_library_sources(tmp_path, tmp_path)

    assert [path.name for path in reports] == [
        "trivy-backend-source-runtime-libraries.json"
    ]
    assert provenance.name == "ditto-backend-source-provenance.spdx.json"
    assert provenance.is_file()
    assert provenance.is_file()


def test_backend_source_scan_pulls_pinned_source_for_buildkit_daemon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = "source@sha256:" + "a" * 64
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> str:
        commands.append(command)
        if command[1:3] == ["image", "inspect"]:
            return source
        if command[1] == "save":
            archive.write_text("archive", encoding="utf-8")
        return ""

    archive = tmp_path / "runtime-libraries.tar"
    report = tmp_path / "report.json"
    monkeypatch.setattr(artifact_gate, "_run", run)
    monkeypatch.setattr(
        artifact_gate, "_select_amd64_archive", lambda _path: "sha256:id"
    )
    monkeypatch.setattr(
        artifact_gate, "_run_ephemeral_container", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        artifact_gate, "_verify_scanner_source", lambda *_args, **_kwargs: None
    )

    artifact_gate._scan_source_archive(
        "docker",
        tmp_path,
        source=source,
        archive=archive,
        output=tmp_path,
        report=report,
    )

    assert commands[0] == ["docker", "pull", "--platform", "linux/amd64", source]
    assert commands[1][1:3] == ["image", "inspect"]
    assert commands[-1][1] == "save"


@pytest.mark.parametrize("matches", [True, False])
def test_source_archive_scan_binds_digest_only_report_to_selected_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matches: bool
) -> None:
    """The release source scan accepts only the independently selected image ID."""
    image_id = "sha256:" + "a" * 64
    report = tmp_path / "trivy-source.json"
    source = "registry/source@sha256:" + "b" * 64
    monkeypatch.setattr(artifact_gate, "_run", lambda *_args, **_kwargs: source)
    monkeypatch.setattr(artifact_gate, "_select_amd64_archive", lambda _path: image_id)

    def scan(*_args: object, **_kwargs: object) -> None:
        report.write_text(
            json.dumps(
                {
                    "Metadata": {
                        "ImageID": image_id if matches else "sha256:" + "c" * 64,
                    }
                }
            )
        )

    monkeypatch.setattr(artifact_gate, "_run_ephemeral_container", scan)
    if matches:
        artifact_gate._scan_source_archive(
            "docker",
            tmp_path,
            source=source,
            archive=tmp_path / "source.tar",
            output=tmp_path,
            report=report,
        )
    else:
        with pytest.raises(artifact_gate.ArtifactGateError, match="pinned image"):
            artifact_gate._scan_source_archive(
                "docker",
                tmp_path,
                source=source,
                archive=tmp_path / "source.tar",
                output=tmp_path,
                report=report,
            )


def _write_json_blob(archive: tarfile.TarFile, payload: object) -> tuple[str, bytes]:
    content = json.dumps(payload, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    member = tarfile.TarInfo(f"blobs/sha256/{digest}")
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))
    return digest, content


@pytest.mark.parametrize(
    ("architecture", "expected"), [("amd64", True), ("arm64", False)]
)
def test_select_amd64_archive_accepts_single_image_manifest(
    tmp_path: Path,
    architecture: str,
    expected: bool,
) -> None:
    archive = tmp_path / "source.tar"
    layer = b"layer"
    layer_digest = hashlib.sha256(layer).hexdigest()

    with tarfile.open(archive, "w") as output:
        config = {"architecture": architecture, "os": "linux"}
        config_digest, _ = _write_json_blob(output, config)
        manifest = {
            "config": {
                "digest": f"sha256:{config_digest}",
                "mediaType": "application/vnd.oci.image.config.v1+json",
            },
            "layers": [{"digest": f"sha256:{layer_digest}"}],
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "schemaVersion": 2,
        }
        manifest_digest, _ = _write_json_blob(output, manifest)
        index = {
            "manifests": [
                {
                    "digest": f"sha256:{manifest_digest}",
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                }
            ],
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "schemaVersion": 2,
        }
        _write_json_blob(output, index)
        index_member = tarfile.TarInfo("index.json")
        index_content = json.dumps(index, separators=(",", ":")).encode()
        index_member.size = len(index_content)
        output.addfile(index_member, io.BytesIO(index_content))
        member = tarfile.TarInfo(f"blobs/sha256/{layer_digest}")
        member.size = len(layer)
        output.addfile(member, io.BytesIO(layer))

    if expected:
        image_id = artifact_gate._select_amd64_archive(archive)
        assert image_id == f"sha256:{config_digest}"
        with tarfile.open(archive) as result:
            manifest_stream = result.extractfile("manifest.json")
            config_stream = result.extractfile(f"blobs/sha256/{config_digest}")
            assert manifest_stream is not None
            assert config_stream is not None
            assert json.load(manifest_stream) == [
                {
                    "Config": f"blobs/sha256/{config_digest}",
                    "Layers": [f"blobs/sha256/{layer_digest}"],
                    "RepoTags": None,
                }
            ]
            assert config_stream.read()
    else:
        with pytest.raises(artifact_gate.ArtifactGateError, match="not linux/amd64"):
            artifact_gate._select_amd64_archive(archive)


def _filesystem_tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, payload in files.items():
            member = tarfile.TarInfo(name.removeprefix("/"))
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


def _vulnerable_report(source: str) -> dict[str, object]:
    return {
        "Metadata": {"RepoDigests": [source]},
        "Results": [
            {
                "Packages": [
                    {
                        "Name": "libssl3t64",
                        "Version": "3.0.0",
                        "Identifier": {"PURL": "pkg:deb/debian/libssl3t64@3.0.0"},
                        "InstalledFiles": ["/usr/lib/libssl.so.3"],
                    }
                ],
                "Vulnerabilities": [{"PkgName": "libssl3t64"}],
            }
        ],
    }


@pytest.mark.parametrize(
    "destination", ["/usr/lib/libssl.so.3", "/lib/libssl.so.3", "/usr/lib/renamed.so"]
)
def test_vulnerable_source_file_cannot_remain_byte_identical(
    tmp_path: Path,
    destination: str,
) -> None:
    source = tmp_path / "source.tar"
    final = tmp_path / "final.tar"
    _filesystem_tar(source, {"/usr/lib/libssl.so.3": b"vulnerable"})
    _filesystem_tar(final, {destination: b"vulnerable"})

    with pytest.raises(
        artifact_gate.ArtifactGateError,
        match=r"byte-identical.*libssl3t64:/usr/lib/libssl.so.3",
    ):
        artifact_gate._verify_vulnerable_source_files(
            _vulnerable_report("source@sha256:" + "a" * 64),
            source_export=source,
            final_export=final,
        )


@pytest.mark.parametrize("link_type", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_vulnerable_library_link_cannot_hide_bytes_outside_library_tree(
    tmp_path: Path,
    link_type: bytes,
) -> None:
    source = tmp_path / "source.tar"
    final = tmp_path / "final.tar"
    _filesystem_tar(source, {"/usr/lib/libssl.so.3": b"vulnerable"})
    _filesystem_tar(final, {"/opt/relocated.so": b"vulnerable"})
    with tarfile.open(final, "a") as archive:
        link = tarfile.TarInfo("lib/libssl.so.3")
        link.type = link_type
        link.linkname = (
            "/opt/relocated.so" if link_type == tarfile.SYMTYPE else "opt/relocated.so"
        )
        archive.addfile(link)
    with pytest.raises(artifact_gate.ArtifactGateError, match="byte-identical"):
        artifact_gate._verify_vulnerable_source_files(
            _vulnerable_report("source@sha256:" + "a" * 64),
            source_export=source,
            final_export=final,
        )


def test_vulnerable_source_file_may_be_absent_or_replaced(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tar"
    final = tmp_path / "final.tar"
    _filesystem_tar(source, {"/usr/lib/libssl.so.3": b"vulnerable"})
    _filesystem_tar(
        final,
        {
            "/usr/lib/libssl.so.3": b"replacement",
            "/usr/lib/other.so": b"clean",
            # Identical non-library content in an independently sourced runtime
            # is not evidence that the copied source library survived.
            "/usr/local/lib/python3.13/unrelated.py": b"vulnerable",
        },
    )

    artifact_gate._verify_vulnerable_source_files(
        _vulnerable_report("source@sha256:" + "a" * 64),
        source_export=source,
        final_export=final,
    )


def test_backend_sbom_links_source_provenance_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sbom = tmp_path / "backend.spdx.json"
    provenance = tmp_path / "source-provenance.spdx.json"
    sbom.write_text(
        json.dumps(
            {
                "documentDescribes": ["SPDXRef-Subject"],
                "packages": [{"SPDXID": "SPDXRef-Subject", "name": "backend"}],
                "relationships": [],
                "spdxVersion": "SPDX-2.3",
            }
        )
    )
    provenance.write_text(
        json.dumps(
            {
                "documentDescribes": ["SPDXRef-backend-source-image-runtime-libraries"],
                "documentNamespace": "https://ditto.invalid/source",
                "packages": [],
                "spdxVersion": "SPDX-2.3",
            }
        )
    )
    monkeypatch.setattr(artifact_gate, "_sha256", lambda _path: "d" * 64)

    artifact_gate._bind_backend_source_provenance(sbom, provenance)

    document = json.loads(sbom.read_text())
    assert document["externalDocumentRefs"] == [
        {
            "checksum": {"algorithm": "SHA256", "checksumValue": "d" * 64},
            "externalDocumentId": "DocumentRef-runtime-libraries",
            "spdxDocument": "https://ditto.invalid/source",
        }
    ]
    assert document["relationships"] == [
        {
            "relatedSpdxElement": (
                "DocumentRef-runtime-libraries:"
                "SPDXRef-backend-source-image-runtime-libraries"
            ),
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-Subject",
        }
    ]


def test_backend_sbom_links_source_provenance_from_syft_describes_relationship(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sbom = tmp_path / "backend.spdx.json"
    provenance = tmp_path / "source-provenance.spdx.json"
    sbom.write_text(
        json.dumps(
            {
                "packages": [{"SPDXID": "SPDXRef-Subject", "name": "backend"}],
                "relationships": [
                    {
                        "relatedSpdxElement": "SPDXRef-Subject",
                        "relationshipType": "DESCRIBES",
                        "spdxElementId": "SPDXRef-DOCUMENT",
                    }
                ],
                "spdxVersion": "SPDX-2.3",
            }
        )
    )
    provenance.write_text(
        json.dumps(
            {
                "documentDescribes": ["SPDXRef-backend-source-image-runtime-libraries"],
                "documentNamespace": "https://ditto.invalid/source",
                "packages": [],
                "spdxVersion": "SPDX-2.3",
            }
        )
    )
    monkeypatch.setattr(artifact_gate, "_sha256", lambda _path: "d" * 64)

    artifact_gate._bind_backend_source_provenance(sbom, provenance)

    document = json.loads(sbom.read_text())
    assert document["documentDescribes"] == ["SPDXRef-Subject"]
    assert document["relationships"][-1] == {
        "relatedSpdxElement": (
            "DocumentRef-runtime-libraries:"
            "SPDXRef-backend-source-image-runtime-libraries"
        ),
        "relationshipType": "DEPENDS_ON",
        "spdxElementId": "SPDXRef-Subject",
    }


@pytest.mark.parametrize("scanner", ["syft", "trivy"])
def test_scanner_subject_mismatch_cannot_pass(tmp_path: Path, scanner: str) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "source": {"metadata": {"imageID": "sha256:wrong"}},
                "Metadata": {"ImageID": "sha256:wrong"},
            }
        )
    )
    with pytest.raises(artifact_gate.ArtifactGateError, match="subject"):
        artifact_gate._verify_scanner_subject(
            report, image="sha256:" + "d" * 64, scanner=scanner
        )


def test_exported_config_digest_is_not_the_oci_index_id(tmp_path: Path) -> None:
    path = tmp_path / "image.tar"
    config = b'{"architecture":"arm64"}'
    with tarfile.open(path, "w") as archive:
        for name, data in (
            ("manifest.json", b'[{"Config":"config.json"}]'),
            ("config.json", config),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    assert (
        artifact_gate._archive_image_config(path)
        == "sha256:" + hashlib.sha256(config).hexdigest()
    )
