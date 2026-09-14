"""Contract tests for the pinned, offline oasdiff wrapper."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tooling.contracts import oasdiff


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603 -- test-only resolved git executable
        [git, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_merge_base_without_canonical_contract_is_explicit_no_baseline(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "initial")

    resolution = oasdiff.resolve_merge_base(
        repo_root=tmp_path,
        base_ref="HEAD",
    )

    assert resolution.status == "no-baseline"
    assert resolution.contract_bytes is None
    assert "contracts/openapi/v1.json" in resolution.reason


def test_merge_base_ignores_legacy_contract_path(
    tmp_path: Path,
) -> None:
    # The pre-migration docs/openapi fallback was retired with the erratum:
    # baselines only resolve from the canonical contracts/openapi path.
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    legacy = tmp_path / "docs/openapi/v1.json"
    legacy.parent.mkdir(parents=True)
    payload = (
        b'{"openapi":"3.1.0","info":{"title":"Legacy","version":"1"},"paths":{}}\n'
    )
    legacy.write_bytes(payload)
    _git(tmp_path, "add", "docs/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "legacy contract")

    resolution = oasdiff.resolve_merge_base(
        repo_root=tmp_path,
        base_ref="HEAD",
    )

    assert resolution.status == "no-baseline"
    assert resolution.contract_bytes is None


def test_merge_base_without_common_ancestor_fails_closed(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-qm", "base history")
    _git(tmp_path, "tag", "base-history")
    _git(tmp_path, "switch", "--orphan", "unrelated")
    (tmp_path / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
    _git(tmp_path, "add", "unrelated.txt")
    _git(tmp_path, "commit", "-qm", "unrelated history")

    with pytest.raises(oasdiff.OasdiffError, match="cannot resolve merge base"):
        oasdiff.resolve_merge_base(
            repo_root=tmp_path,
            base_ref="base-history",
        )


def test_merge_base_command_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "initial")
    original_git = oasdiff._git

    def fail_merge_base(
        repo_root: Path,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        if arguments and arguments[0] == "merge-base":
            command = ["git", *arguments]
            return subprocess.CompletedProcess(
                command,
                returncode=128,
                stdout=b"",
                stderr=b"fatal: shallow history cannot resolve merge base\n",
            )
        return original_git(repo_root, *arguments, check=check)

    monkeypatch.setattr(oasdiff, "_git", fail_merge_base)

    with pytest.raises(
        oasdiff.OasdiffError,
        match="shallow history cannot resolve merge base",
    ):
        oasdiff.resolve_merge_base(repo_root=tmp_path, base_ref="HEAD")


def test_release_ignores_legacy_contract_path(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    legacy = tmp_path / "docs/openapi/v1.json"
    legacy.parent.mkdir(parents=True)
    payload = (
        b'{"openapi":"3.1.0","info":{"title":"Legacy","version":"1"},"paths":{}}\n'
    )
    legacy.write_bytes(payload)
    _git(tmp_path, "add", "docs/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "legacy release contract")
    _git(tmp_path, "tag", "v0.9.0")

    resolution = oasdiff.resolve_release(repo_root=tmp_path)

    assert resolution.status == "no-baseline"
    assert resolution.ref == "v0.9.0"
    assert resolution.contract_bytes is None


def test_release_uses_latest_reachable_tag_without_stale_fallback(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Contract Test")
    _git(tmp_path, "config", "user.email", "contract@example.invalid")
    contract = tmp_path / "contracts/openapi/v1.json"
    contract.parent.mkdir(parents=True)
    contract.write_text('{"openapi":"3.1.0"}\n', encoding="utf-8")
    _git(tmp_path, "add", "contracts/openapi/v1.json")
    _git(tmp_path, "commit", "-qm", "release with contract")
    _git(tmp_path, "tag", "v1.0.0")
    contract.unlink()
    _git(tmp_path, "add", "-u")
    _git(tmp_path, "commit", "-qm", "latest release without contract")
    _git(tmp_path, "tag", "v2.0.0")

    resolution = oasdiff.resolve_release(repo_root=tmp_path)

    assert resolution.status == "no-baseline"
    assert resolution.ref == "v2.0.0"
    assert "v2.0.0" in resolution.reason


def test_tampered_checksum_manifest_is_rejected_before_archive(
    tmp_path: Path,
) -> None:
    checksums = tmp_path / "checksums.txt"
    checksums.write_text("not trusted\n", encoding="utf-8")
    expected = hashlib.sha256(b"trusted manifest\n").hexdigest()

    with pytest.raises(oasdiff.SupplyChainError, match=r"checksums\.txt SHA-256"):
        oasdiff.verify_release_archive(
            dist_dir=tmp_path,
            asset_name="oasdiff_1.28.0_linux_amd64.tar.gz",
            expected_manifest_sha256=expected,
        )


def test_release_archive_is_accepted_only_through_trusted_manifest(
    tmp_path: Path,
) -> None:
    asset_name = "oasdiff_1.28.0_linux_amd64.tar.gz"
    archive = tmp_path / asset_name
    archive.write_bytes(b"verified archive payload")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_payload = f"{archive_sha}  {asset_name}\n".encode()
    (tmp_path / "checksums.txt").write_bytes(manifest_payload)

    verified = oasdiff.verify_release_archive(
        dist_dir=tmp_path,
        asset_name=asset_name,
        expected_manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
    )

    assert verified == archive


def test_breaking_check_fails_on_warnings_without_loading_repo_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = b'{"openapi":"3.1.0","info":{"title":"T","version":"1"},"paths":{}}'
    current = tmp_path / "current.json"
    current.write_bytes(schema)
    resolution = oasdiff.BaselineResolution(
        kind="merge-base",
        status="found",
        ref="main",
        commit="a" * 40,
        reason="test baseline",
        contract_bytes=schema,
    )
    observed: dict[str, object] = {}

    @contextmanager
    def fake_verified_oasdiff(_dist_dir: Path) -> Iterator[Path]:
        yield tmp_path / "oasdiff"

    def fake_run(
        command: list[str],
        **options: object,
    ) -> subprocess.CompletedProcess[bytes]:
        observed["command"] = command
        observed["cwd"] = options["cwd"]
        observed["baseline"] = Path(command[2]).read_bytes()
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(oasdiff, "verified_oasdiff", fake_verified_oasdiff)
    monkeypatch.setattr(oasdiff.subprocess, "run", fake_run)

    assert (
        oasdiff.run_breaking_check(
            resolution=resolution,
            current_path=current,
            dist_dir=tmp_path,
        )
        == 0
    )

    command = observed["command"]
    assert isinstance(command, list)
    assert command[command.index("--fail-on") + 1] == "WARN"
    assert observed["cwd"] != oasdiff._REPO_ROOT
    assert observed["baseline"] == schema


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "oasdiff_1.28.0_darwin_all.tar.gz"),
        ("Darwin", "x86_64", "oasdiff_1.28.0_darwin_all.tar.gz"),
        ("Linux", "x86_64", "oasdiff_1.28.0_linux_amd64.tar.gz"),
        ("Linux", "aarch64", "oasdiff_1.28.0_linux_arm64.tar.gz"),
        ("Windows", "AMD64", "oasdiff_1.28.0_windows_amd64.tar.gz"),
    ],
)
def test_release_asset_selection_is_platform_specific(
    system: str,
    machine: str,
    expected: str,
) -> None:
    assert oasdiff.release_asset_name(system=system, machine=machine) == expected
