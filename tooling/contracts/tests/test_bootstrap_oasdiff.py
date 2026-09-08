"""Self-contained, checksum-pinned oasdiff toolchain bootstrap contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tooling.contracts import bootstrap_oasdiff, check_contract, oasdiff


def test_bootstrap_downloads_once_into_a_content_addressed_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    asset_name = "oasdiff_1.28.0_linux_amd64.tar.gz"
    archive = b"authenticated oasdiff archive"
    manifest = f"{hashlib.sha256(archive).hexdigest()}  {asset_name}\n".encode()
    monkeypatch.setattr(
        bootstrap_oasdiff,
        "_CHECKSUMS_SHA256",
        hashlib.sha256(manifest).hexdigest(),
    )
    requests: list[str] = []

    def download(url: str, *, limit: int = 0) -> bytes:
        del limit
        requests.append(url)
        return manifest if url.endswith("/checksums.txt") else archive

    monkeypatch.setattr(bootstrap_oasdiff, "_download", download)

    first = bootstrap_oasdiff.ensure_distribution(
        cache_root=tmp_path,
        system="Linux",
        machine="x86_64",
    )
    second = bootstrap_oasdiff.ensure_distribution(
        cache_root=tmp_path,
        system="Linux",
        machine="x86_64",
    )

    assert first == second
    assert first.name == hashlib.sha256(manifest).hexdigest()
    assert (first / "checksums.txt").read_bytes() == manifest
    assert (first / asset_name).read_bytes() == archive
    assert len(requests) == 2
    assert (
        oasdiff.verify_release_archive(
            dist_dir=first,
            asset_name=asset_name,
            expected_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        )
        == first / asset_name
    )


def test_bootstrap_repairs_a_corrupt_cached_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    asset_name = "oasdiff_1.28.0_linux_amd64.tar.gz"
    archive = b"authenticated oasdiff archive"
    manifest = f"{hashlib.sha256(archive).hexdigest()}  {asset_name}\n".encode()
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    monkeypatch.setattr(bootstrap_oasdiff, "_CHECKSUMS_SHA256", manifest_sha)
    target = tmp_path / f"v{oasdiff.OASDIFF_VERSION}" / manifest_sha
    target.mkdir(parents=True)
    (target / "checksums.txt").write_bytes(manifest)
    (target / asset_name).write_bytes(b"corrupt")
    requests: list[str] = []

    def download(url: str, *, limit: int = 0) -> bytes:
        del limit
        requests.append(url)
        return archive

    monkeypatch.setattr(bootstrap_oasdiff, "_download", download)

    assert (
        bootstrap_oasdiff.ensure_distribution(
            cache_root=tmp_path,
            system="Linux",
            machine="x86_64",
        )
        == target
    )
    assert (target / asset_name).read_bytes() == archive
    assert len(requests) == 1


def test_contract_gate_resolves_prepared_distribution_without_bootstrapping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DITTO_OASDIFF_DIST_DIR", raising=False)
    observed: dict[str, str] = {}

    def prepared_distribution(*, system: str, machine: str) -> Path:
        observed.update(system=system, machine=machine)
        return tmp_path

    monkeypatch.setattr(
        bootstrap_oasdiff,
        "prepared_distribution",
        prepared_distribution,
    )
    monkeypatch.setattr(check_contract.platform, "system", lambda: "TestOS")
    monkeypatch.setattr(check_contract.platform, "machine", lambda: "test-arch")

    assert check_contract._dist_dir(None) == tmp_path
    assert observed == {"system": "TestOS", "machine": "test-arch"}


def test_default_cache_is_outside_the_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DITTO_TOOL_CACHE_ROOT", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "user-cache"))
    monkeypatch.setattr(bootstrap_oasdiff.sys, "platform", "linux")

    target = bootstrap_oasdiff._default_cache_root()

    assert target == tmp_path / "user-cache" / "ditto" / "tools" / "oasdiff"
    assert not target.is_relative_to(bootstrap_oasdiff._REPO_ROOT)
