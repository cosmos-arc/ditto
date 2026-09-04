"""Machine-readable Gate evidence manifest contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_apps.operations.evidence_manifest import (
    EvidenceManifestError,
    build_gate_manifest,
    verify_gate_manifest,
    write_gate_manifest,
)


def test_gate_manifest_hashes_and_revalidates_every_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "q0.json"
    artifact.parent.mkdir()
    artifact.write_text('{"status":"passed"}\n', encoding="utf-8")

    manifest = build_gate_manifest(tmp_path, "Q0", (artifact,))
    manifest_path = tmp_path / "manifests" / "Q0.json"
    write_gate_manifest(manifest_path, manifest)

    verified = verify_gate_manifest(tmp_path, manifest_path)

    assert verified == manifest
    assert verified.status == "passed"
    assert verified.artifacts[0].relative_path == "reports/q0.json"
    assert verified.artifacts[0].sha256.startswith("sha256:")
    assert verified.manifest_hash.startswith("sha256:")


def test_gate_manifest_detects_artifact_tamper(tmp_path: Path) -> None:
    artifact = tmp_path / "gate-input.json"
    artifact.write_text("original", encoding="utf-8")
    manifest_path = tmp_path / "Q1-manifest.json"
    write_gate_manifest(
        manifest_path,
        build_gate_manifest(tmp_path, "Q1", (artifact,)),
    )
    artifact.write_text("tampered", encoding="utf-8")

    with pytest.raises(EvidenceManifestError, match="artifact hash mismatch"):
        verify_gate_manifest(tmp_path, manifest_path)


def test_blocked_gate_requires_explicit_blockers(tmp_path: Path) -> None:
    artifact = tmp_path / "q6.json"
    artifact.write_text("{}", encoding="utf-8")

    manifest = build_gate_manifest(
        tmp_path,
        "Q6",
        (artifact,),
        blockers=("20 real A-share trading days have not elapsed",),
    )

    assert manifest.status == "blocked"
    assert manifest.blockers == ("20 real A-share trading days have not elapsed",)


def test_manifest_rejects_artifact_outside_evidence_root(tmp_path: Path) -> None:
    artifact = tmp_path.parent / "outside.json"
    artifact.write_text("{}", encoding="utf-8")

    with pytest.raises(EvidenceManifestError, match="outside evidence root"):
        build_gate_manifest(tmp_path, "Q0", (artifact,))
