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
from tooling.release.artifact_gate import ReleaseCoordinates

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
        "_stage_web_dependency_metadata",
        "_bind_and_verify_web_sbom",
    ):
        monkeypatch.setattr(artifact_gate, name, noop)
    monkeypatch.setattr(artifact_gate, "_smoke_container", smoke)
    with pytest.raises(SmokeObserved):
        artifact_gate.run_artifact_gate(tmp_path)


def _write_json_blob(archive: tarfile.TarFile, payload: object) -> tuple[str, bytes]:
    content = json.dumps(payload, separators=(",", ":")).encode()
    digest = hashlib.sha256(content).hexdigest()
    member = tarfile.TarInfo(f"blobs/sha256/{digest}")
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))
    return digest, content


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
