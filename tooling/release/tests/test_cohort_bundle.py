"""Tests for the deterministic, self-verifying release delivery envelope."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tooling.release.cohort_bundle import (
    CohortBundleError,
    create_release_bundle,
    stage_offline_verifier,
)
from tooling.release.cohort_manifest import (
    ReleaseCoordinates,
    build_cohort_manifest,
    write_cohort_manifest,
)

ROOT = Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cohort(root: Path) -> tuple[Path, list[str]]:
    contract = root / "release-inputs" / "contracts" / "openapi" / "v1.json"
    pixi_lock = root / "release-inputs" / "pixi.lock"
    bun_lock = root / "release-inputs" / "bun.lock"
    backend = root / "ditto-image.tar"
    web = root / "ditto-web.tar"
    backend_sbom = root / "ditto-backend.spdx.json"
    web_sbom = root / "ditto-web.spdx.json"
    policy = (
        root / "release-inputs" / "contracts" / "cohorts" / "compatibility-policy.json"
    )
    policy_digest = policy.with_suffix(".sha256")
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b'{"openapi":"3.1.0"}\n')
    pixi_lock.write_bytes(b"pixi\n")
    bun_lock.write_bytes(b"bun\n")
    backend.write_bytes(b"backend\n")
    web.write_bytes(b"web\n")
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
                                "checksumValue": _sha256(web),
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
    policy.parent.mkdir(parents=True, exist_ok=True)
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
    policy_digest.write_text(
        f"{_sha256(policy)}  compatibility-policy.json\n",
        encoding="utf-8",
    )
    verifier_files = stage_offline_verifier(
        source_root=ROOT,
        workspace_root=root,
    )
    artifacts = (
        contract,
        pixi_lock,
        bun_lock,
        backend,
        web,
        backend_sbom,
        web_sbom,
        policy,
        policy_digest,
        *verifier_files,
    )
    manifest = build_cohort_manifest(
        workspace_root=root,
        artifact_paths=artifacts,
        backend_artifact_path=backend,
        web_artifact_path=web,
        release=ReleaseCoordinates(
            product_version="1.2.3",
            git_sha="a" * 40,
            api_contract_version="v1",
            api_contract_sha256=_sha256(contract),
            generated_at="2026-09-05T00:00:00Z",
        ),
    )
    manifest_path = root / "release-cohort.json"
    write_cohort_manifest(manifest_path, manifest, artifact_paths=artifacts)
    return manifest_path, [record["path"] for record in manifest["artifacts"]]


def test_bundle_is_deterministic_preserves_paths_and_runs_its_bound_verifier(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_paths = _cohort(tmp_path)
    policy = tmp_path / "next-cohort-policy" / "compatibility-policy.json"
    digest = policy.with_suffix(".sha256")
    policy.parent.mkdir()
    policy.write_text('{"schema":"policy"}\n')
    digest.write_text(f"{'0' * 64}  compatibility-policy.json\n")
    first = tmp_path / "ditto-release-cohort.tar"
    second = tmp_path / "same-cohort.tar"

    create_release_bundle(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        output_path=first,
        additional_paths=(policy, digest),
        source_date_epoch=1_788_566_400,
    )
    create_release_bundle(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        output_path=second,
        additional_paths=(policy, digest),
        source_date_epoch=1_788_566_400,
    )

    assert first.read_bytes() == second.read_bytes()
    expected = sorted(
        [
            *artifact_paths,
            "release-cohort.json",
            "next-cohort-policy/compatibility-policy.json",
            "next-cohort-policy/compatibility-policy.sha256",
        ]
    )
    with tarfile.open(first, mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == expected
        assert first.name not in expected
        assert all(member.isfile() for member in members)
        assert all(member.uid == member.gid == 0 for member in members)
        assert all(member.uname == member.gname == "" for member in members)
        assert all(member.mode == 0o644 for member in members)
        assert all(member.mtime == 1_788_566_400 for member in members)
        extracted = tmp_path / "extracted"
        archive.extractall(extracted, filter="data")

    result = subprocess.run(
        [
            sys.executable,
            "release-tools/verify-cohort.py",
            "--workspace-root",
            ".",
            "--manifest",
            "release-cohort.json",
        ],
        cwd=extracted,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "cohort-verify: PASS" in result.stdout


def test_bundle_rejects_escape_symlink_and_recursive_self_inclusion(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _cohort(tmp_path)
    outside = tmp_path.parent / "outside-evidence.json"
    outside.write_text("{}\n")
    symlink = tmp_path / "linked-evidence.json"
    symlink.symlink_to(outside)
    try:
        with pytest.raises(CohortBundleError, match="escape"):
            create_release_bundle(
                workspace_root=tmp_path,
                manifest_path=manifest_path,
                output_path=tmp_path / "escape.tar",
                additional_paths=(outside,),
                source_date_epoch=0,
            )
        with pytest.raises(CohortBundleError, match="symlink"):
            create_release_bundle(
                workspace_root=tmp_path,
                manifest_path=manifest_path,
                output_path=tmp_path / "symlink.tar",
                additional_paths=(symlink,),
                source_date_epoch=0,
            )
        with pytest.raises(CohortBundleError, match=r"output|itself"):
            create_release_bundle(
                workspace_root=tmp_path,
                manifest_path=manifest_path,
                output_path=tmp_path / "ditto-image.tar",
                source_date_epoch=0,
            )
    finally:
        symlink.unlink()
        outside.unlink()


def test_staged_verifier_is_an_exact_minimal_stdlib_only_package(
    tmp_path: Path,
) -> None:
    staged = stage_offline_verifier(source_root=ROOT, workspace_root=tmp_path)

    relative = [path.relative_to(tmp_path).as_posix() for path in staged]
    assert relative == [
        "release-tools/tooling/__init__.py",
        "release-tools/tooling/release/__init__.py",
        "release-tools/tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_verify.py",
        "release-tools/verify-cohort.py",
    ]
    source_by_destination = {
        "release-tools/tooling/__init__.py": ROOT / "tooling" / "__init__.py",
        "release-tools/tooling/release/__init__.py": (
            ROOT / "tooling" / "release" / "__init__.py"
        ),
        "release-tools/tooling/release/cohort_manifest.py": (
            ROOT / "tooling" / "release" / "cohort_manifest.py"
        ),
        "release-tools/tooling/release/cohort_verify.py": (
            ROOT / "tooling" / "release" / "cohort_verify.py"
        ),
        "release-tools/verify-cohort.py": (
            ROOT / "tooling" / "release" / "offline_verify.py"
        ),
    }
    for path in staged:
        source = source_by_destination[path.relative_to(tmp_path).as_posix()]
        assert path.read_bytes() == source.read_bytes()
