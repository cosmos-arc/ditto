"""Tests for deterministic, fail-closed release cohort manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tooling.release.cohort_manifest import (
    CohortManifestError,
    ReleaseCoordinates,
    build_cohort_manifest,
    main,
    write_cohort_manifest,
)


def _release(
    *,
    product_version: str = "1.2.3",
    git_sha: str = "a" * 40,
    api_contract_sha256: str,
) -> ReleaseCoordinates:
    return ReleaseCoordinates(
        product_version=product_version,
        git_sha=git_sha,
        api_contract_version="v1",
        api_contract_sha256=api_contract_sha256,
        generated_at="2026-09-04T00:00:00Z",
    )


def test_manifest_is_deterministic_and_binds_every_artifact(tmp_path: Path) -> None:
    contract = tmp_path / "contracts" / "openapi.json"
    image = tmp_path / "dist" / "ditto-image.tar"
    web = tmp_path / "dist" / "ditto-web.tar"
    contract.parent.mkdir()
    image.parent.mkdir()
    contract.write_bytes(b'{"openapi":"3.1.0"}\n')
    image.write_bytes(b"immutable-image")
    web.write_bytes(b"immutable-web")
    contract_sha256 = hashlib.sha256(contract.read_bytes()).hexdigest()

    first = build_cohort_manifest(
        workspace_root=tmp_path,
        artifact_paths=(image, web, contract),
        backend_artifact_path=image,
        web_artifact_path=web,
        release=_release(api_contract_sha256=contract_sha256),
    )
    second = build_cohort_manifest(
        workspace_root=tmp_path,
        artifact_paths=(contract, web, image),
        backend_artifact_path=image,
        web_artifact_path=web,
        release=_release(api_contract_sha256=contract_sha256),
    )

    assert first == second
    assert first["schema"] == "ditto.release-cohort"
    assert first["schema_version"] == 1
    assert first["release"]["git_sha"] == "a" * 40
    assert first["release"]["api_contract_sha256"] == contract_sha256
    assert first["backend_artifact"]["path"] == "dist/ditto-image.tar"
    assert first["web_artifact"]["path"] == "dist/ditto-web.tar"
    assert [item["path"] for item in first["artifacts"]] == [
        "contracts/openapi.json",
        "dist/ditto-image.tar",
        "dist/ditto-web.tar",
    ]
    assert all(len(item["sha256"]) == 64 for item in first["artifacts"])
    assert len(first["cohort_id"]) == 64


def test_manifest_rejects_artifacts_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-release-artifact"
    outside.write_bytes(b"outside")
    try:
        with pytest.raises(CohortManifestError, match="workspace"):
            build_cohort_manifest(
                workspace_root=tmp_path,
                artifact_paths=(outside,),
                backend_artifact_path=outside,
                web_artifact_path=outside,
                release=_release(git_sha="b" * 40, api_contract_sha256="0" * 64),
            )
    finally:
        outside.unlink()


def test_manifest_rejects_symlink_artifacts(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"target")
    link = tmp_path / "artifact"
    link.symlink_to(target)

    with pytest.raises(CohortManifestError, match="symlink"):
        build_cohort_manifest(
            workspace_root=tmp_path,
            artifact_paths=(link,),
            backend_artifact_path=link,
            web_artifact_path=link,
            release=_release(git_sha="c" * 40, api_contract_sha256="0" * 64),
        )


def test_manifest_rejects_unverifiable_release_identity(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"artifact")

    with pytest.raises(CohortManifestError, match="git SHA"):
        build_cohort_manifest(
            workspace_root=tmp_path,
            artifact_paths=(artifact,),
            backend_artifact_path=artifact,
            web_artifact_path=artifact,
            release=_release(
                git_sha="main",
                api_contract_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            ),
        )

    for invalid_version in ("01.2.3", "1.2.3.4", "v1.2.3", "1.2"):
        with pytest.raises(CohortManifestError, match="SemVer"):
            build_cohort_manifest(
                workspace_root=tmp_path,
                artifact_paths=(artifact,),
                backend_artifact_path=artifact,
                web_artifact_path=artifact,
                release=_release(
                    product_version=invalid_version,
                    api_contract_sha256=hashlib.sha256(
                        artifact.read_bytes()
                    ).hexdigest(),
                ),
            )


def test_manifest_rejects_contract_digest_not_bound_to_an_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "contract.json"
    artifact.write_text("{}\n")

    with pytest.raises(CohortManifestError, match="contract digest"):
        build_cohort_manifest(
            workspace_root=tmp_path,
            artifact_paths=(artifact,),
            backend_artifact_path=artifact,
            web_artifact_path=artifact,
            release=_release(git_sha="f" * 40, api_contract_sha256="0" * 64),
        )


def test_write_manifest_is_canonical_and_refuses_artifact_overwrite(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    manifest = build_cohort_manifest(
        workspace_root=tmp_path,
        artifact_paths=(artifact,),
        backend_artifact_path=artifact,
        web_artifact_path=artifact,
        release=_release(
            git_sha="d" * 40,
            api_contract_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        ),
    )
    output = tmp_path / "dist" / "release-cohort.json"

    write_cohort_manifest(output, manifest, artifact_paths=(artifact,))

    payload = output.read_bytes()
    assert payload.endswith(b"\n")
    assert json.loads(payload) == manifest
    with pytest.raises(CohortManifestError, match="artifact"):
        write_cohort_manifest(artifact, manifest, artifact_paths=(artifact,))


def test_cli_writes_a_complete_manifest_relative_to_workspace(tmp_path: Path) -> None:
    artifact = tmp_path / "contract.json"
    artifact.write_text("{}\n")

    result = main(
        [
            "--workspace-root",
            str(tmp_path),
            "--artifact",
            "contract.json",
            "--backend-artifact",
            "contract.json",
            "--web-artifact",
            "contract.json",
            "--product-version",
            "1.2.3",
            "--git-sha",
            "e" * 40,
            "--api-contract-version",
            "v1",
            "--api-contract-sha256",
            hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "--generated-at",
            "2026-09-04T00:00:00Z",
            "--output",
            "dist/release-cohort.json",
        ]
    )

    assert result == 0
    payload = json.loads((tmp_path / "dist" / "release-cohort.json").read_bytes())
    assert payload["artifacts"][0]["path"] == "contract.json"
    assert payload["backend_artifact"]["path"] == "contract.json"
    assert payload["web_artifact"]["path"] == "contract.json"
