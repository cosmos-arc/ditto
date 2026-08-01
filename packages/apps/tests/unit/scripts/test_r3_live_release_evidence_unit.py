"""Contracts for the cross-repository Task 18 live release evidence bundle."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from ditto_apps.registry.live.r3_live_release_evidence import (
    LiveReleaseEvidenceRequest,
    build_live_release_evidence,
)


def _canonical(value: object) -> bytes:
    return (
        orjson.dumps(value, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    )


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_lane(root: Path, lane: str, *, suffix: str) -> dict[str, object]:
    planning = {
        "cost_model": {
            "bytes_per_run": 1024,
            "bytes_per_trading_session": 16,
        },
        "seed": 42,
        "snapshot": {
            "manifest_hash": suffix * 64,
            "snapshot_id": f"snapshot:{lane}",
        },
        "strategy": {
            "spec_hash": ("a" if lane == "stock" else "b") * 64,
            "strategy_id": f"strategy:{lane}",
            "version": 2,
        },
    }
    planning_path = root / "planning" / lane / f"{suffix * 64}.json"
    _write(planning_path, planning)
    planning_hash = hashlib.sha256(
        orjson.dumps(planning, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    result = {
        "lane": lane,
        "parameter_hash": "c" * 64,
        "planning_document_hash": planning_hash,
        "planning_document_path": planning_path.relative_to(root).as_posix(),
        "registry_hash": "e" * 64,
        "review_bundle_hash": "f" * 64,
        "snapshot_manifest_hash": suffix * 64,
        "strategy_spec_hash": planning["strategy"]["spec_hash"],
    }
    result_path = root / "lanes" / lane / "results" / f"{suffix * 64}.json"
    result_hash = _write(result_path, result)
    _write(
        root / "lanes" / lane / "current.json",
        {
            "lane": lane,
            "relative_path": result_path.relative_to(root).as_posix(),
            "sha256": result_hash,
        },
    )
    return planning


def _request(tmp_path: Path) -> tuple[LiveReleaseEvidenceRequest, dict[str, object]]:
    backend_repo = tmp_path / "backend"
    frontend_repo = tmp_path / "frontend"
    backend_live = tmp_path / "runtime" / "r3-live"
    frontend_live = frontend_repo / "docs" / "review" / "r3" / "live"
    backend_repo.mkdir()
    frontend_repo.mkdir()

    planning = _write_lane(backend_live, "stock", suffix="1")
    _write_lane(backend_live, "etf", suffix="2")
    _write(backend_live / "governance" / f"{'3' * 64}.json", {"actor": "chevy"})
    _write(backend_live / "recovery" / f"{'4' * 64}.json", {"domain_matches": True})

    r2_dir = backend_repo / "artifacts" / "acceptance"
    r2_report = r2_dir / "r2-report.json"
    r2_report_hash = _write(r2_report, {"mode": "live", "status": "ready"})
    group_path = r2_dir / "r2-live-evidence" / "provider-entitlement.json"
    group_hash = _write(group_path, {"kind": "provider_entitlement"})
    r2_manifest = r2_dir / "r2-report.manifest.json"
    _write(
        r2_manifest,
        {
            "groups": {
                "idempotency": [
                    {
                        "relative_path": group_path.relative_to(r2_dir).as_posix(),
                        "sha256": group_hash,
                    }
                ],
                "performance": [
                    {
                        "relative_path": group_path.relative_to(r2_dir).as_posix(),
                        "sha256": group_hash,
                    }
                ],
                "provider_entitlement": [
                    {
                        "relative_path": group_path.relative_to(r2_dir).as_posix(),
                        "sha256": group_hash,
                    }
                ],
                "recoverability": [
                    {
                        "relative_path": group_path.relative_to(r2_dir).as_posix(),
                        "sha256": group_hash,
                    }
                ],
            },
            "report": {"relative_path": r2_report.name, "sha256": r2_report_hash},
            "schema": "ditto.r2-live-gate-source",
            "version": 1,
        },
    )

    r3_report = backend_repo / "artifacts" / "acceptance" / "r3-report.json"
    _write(
        r3_report,
        {
            "generated_at": "2026-08-01T09:00:00Z",
            "mode": "real_data",
            "passed": True,
            "release_status": "RELEASE_ACCEPTANCE_PASSED",
            "source_commit": "a" * 40,
        },
    )
    openapi = backend_repo / "docs" / "openapi" / "v1.json"
    _write(openapi, {"openapi": "3.1.0"})

    browser_report = frontend_live / "report.json"
    browser_report_hash = _write(
        browser_report,
        {
            "generated_at": "2026-08-01T09:05:00Z",
            "mode": "real_data",
            "passed": True,
            "release_status": "RELEASE_ACCEPTANCE_PASSED",
            "source_commit": "b" * 40,
        },
    )
    screenshot = frontend_live / "01-studio.png"
    screenshot.write_bytes(b"png")
    screenshot_hash = hashlib.sha256(b"png").hexdigest()
    browser_manifest = frontend_live / "manifest.json"
    _write(
        browser_manifest,
        {
            "entries": [
                {
                    "relative_path": browser_report.relative_to(
                        frontend_repo
                    ).as_posix(),
                    "sha256": browser_report_hash,
                },
                {
                    "relative_path": screenshot.relative_to(frontend_repo).as_posix(),
                    "sha256": screenshot_hash,
                },
            ],
            "generated_at": "2026-08-01T09:05:00Z",
            "mode": "real_data",
            "schema": "ditto.r3-research-frontend-evidence-manifest",
            "source_commit": "b" * 40,
            "version": 2,
        },
    )

    request = LiveReleaseEvidenceRequest(
        backend_repo=backend_repo,
        frontend_repo=frontend_repo,
        backend_live_evidence_root=backend_live,
        frontend_live_evidence_root=frontend_live,
        r2_report=r2_report,
        r2_source_manifest=r2_manifest,
        r3_report=r3_report,
        openapi_path=openapi,
        r2_archive_root=backend_repo / "docs" / "evidence" / "r2" / "20260801T090000Z",
        r3_archive_root=backend_repo / "docs" / "evidence" / "r3" / "20260801T090000Z",
        output=backend_repo / "docs" / "evidence" / "r3" / "manifest.json",
        backend_commit="a" * 40,
        frontend_commit="b" * 40,
        r2_command="r2-live-command",
        r3_command="r3-live-command",
        frontend_command="frontend-live-command",
    )
    return request, planning


def test_final_bundle_archives_redacted_evidence_and_binds_all_release_identities(
    tmp_path: Path,
) -> None:
    request, stock_planning = _request(tmp_path)

    manifest = build_live_release_evidence(
        request,
        generated_at=datetime(2026, 8, 1, 9, 10, tzinfo=UTC),
    )

    assert manifest["schema"] == "ditto.r3-live-release-evidence-manifest"
    assert manifest["version"] == 1
    assert manifest["backend_commit"] == "a" * 40
    assert manifest["frontend_commit"] == "b" * 40
    assert (
        manifest["openapi_hash"]
        == hashlib.sha256(request.openapi_path.read_bytes()).hexdigest()
    )
    assert (
        manifest["r2_report_hash"]
        == hashlib.sha256(request.r2_report.read_bytes()).hexdigest()
    )
    assert (
        manifest["r2_manifest_hash"]
        == hashlib.sha256(request.r2_source_manifest.read_bytes()).hexdigest()
    )

    stock = manifest["lanes"]["stock"]
    expected_cost_hash = hashlib.sha256(
        orjson.dumps(stock_planning["cost_model"], option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    assert stock == {
        "backend_commit": "a" * 40,
        "cost_hash": expected_cost_hash,
        "frontend_commit": "b" * 40,
        "openapi_hash": manifest["openapi_hash"],
        "packet_bundle_hash": "f" * 64,
        "parameter_hash": "c" * 64,
        "planning_document_hash": hashlib.sha256(
            orjson.dumps(stock_planning, option=orjson.OPT_SORT_KEYS)
        ).hexdigest(),
        "planning_document_sha256": hashlib.sha256(
            (
                request.backend_live_evidence_root
                / "planning"
                / "stock"
                / f"{'1' * 64}.json"
            ).read_bytes()
        ).hexdigest(),
        "registry_hash": "e" * 64,
        "seed": 42,
        "snapshot_hash": "1" * 64,
        "strategy_spec_hash": "a" * 64,
    }

    required = {
        "command",
        "generated_at",
        "mode",
        "relative_path",
        "repository",
        "sha256",
        "source_commit",
    }
    assert manifest["artifacts"]
    assert all(required <= set(item) for item in manifest["artifacts"])
    assert request.output.is_file()
    assert (request.r2_archive_root / "manifest.json").is_file()
    assert any(request.r3_archive_root.rglob("*.json"))


def test_final_bundle_fails_closed_on_browser_artifact_hash_drift(
    tmp_path: Path,
) -> None:
    request, _ = _request(tmp_path)
    (request.frontend_live_evidence_root / "01-studio.png").write_bytes(b"drift")

    with pytest.raises(ValueError, match="frontend evidence hash drift"):
        build_live_release_evidence(request)
