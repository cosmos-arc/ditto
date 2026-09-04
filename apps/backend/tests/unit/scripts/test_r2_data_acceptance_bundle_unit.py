"""Content-addressed output contract for the R2 live acceptance runner."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import orjson
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    R2LiveGateArtifactSource,
    R2LiveGateEvidenceSource,
)
from ditto_apps.scripts.r2_data_acceptance import (
    run_fixture_acceptance,
    write_live_evidence_bundle,
)


def _entry_source(root: Path, value: object) -> R2LiveGateArtifactSource:
    assert isinstance(value, dict)
    path = root / str(value["relative_path"])
    return R2LiveGateArtifactSource(
        path=path,
        artifact_uri=path.resolve().as_uri(),
        expected_content_hash=str(value["sha256"]),
    )


def test_live_bundle_writes_report_four_groups_and_verifiable_manifest(
    tmp_path: Path,
) -> None:
    fixture = run_fixture_acceptance(checked_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC))
    report = replace(fixture, mode="live")
    output = tmp_path / "r2-report.json"
    manifest = tmp_path / "r2-report.manifest.json"

    write_live_evidence_bundle(
        report=report,
        output=output,
        source_manifest=manifest,
    )

    payload = orjson.loads(manifest.read_bytes())
    assert payload["schema"] == "ditto.r2-live-gate-source"
    assert payload["version"] == 1
    assert set(payload["groups"]) == {
        "provider_entitlement",
        "performance",
        "recoverability",
        "idempotency",
    }
    assert all(payload["groups"].values())
    entries = [
        payload["report"],
        *(item for group in payload["groups"].values() for item in group),
    ]
    assert all(".." not in Path(item["relative_path"]).parts for item in entries)
    assert all(
        hashlib.sha256((tmp_path / item["relative_path"]).read_bytes()).hexdigest()
        == item["sha256"]
        for item in entries
    )

    groups = payload["groups"]
    source = R2LiveGateEvidenceSource(
        report_path=output,
        report_uri=output.resolve().as_uri(),
        expected_report_hash=str(payload["report"]["sha256"]),
        provider_entitlement_artifacts=tuple(
            _entry_source(tmp_path, item) for item in groups["provider_entitlement"]
        ),
        performance_artifacts=tuple(
            _entry_source(tmp_path, item) for item in groups["performance"]
        ),
        recoverability_artifacts=tuple(
            _entry_source(tmp_path, item) for item in groups["recoverability"]
        ),
        idempotency_artifacts=tuple(
            _entry_source(tmp_path, item) for item in groups["idempotency"]
        ),
    )
    verified = FileR2LiveGateEvidenceReader(source).read_verified_live_gate()
    assert verified is not None
    assert verified.status == "ready"

    serialized = b"".join(
        (tmp_path / item["relative_path"]).read_bytes() for item in entries
    )
    assert b"token" not in serialized.lower()
    assert b"secret" not in serialized.lower()
