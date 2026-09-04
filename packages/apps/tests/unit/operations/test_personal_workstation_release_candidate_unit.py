"""OPS-10 release-candidate bundle contract tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_apps.operations.evidence_manifest import (
    GateName,
    build_gate_manifest,
    write_gate_manifest,
)
from ditto_apps.operations.personal_workstation_release_candidate import (
    ReleaseCandidateArtifactPaths,
    build_release_candidate_bundle,
)
from ditto_apps.operations.q4_live_account_acceptance import canonical_hash


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
    return path


def _self_hashed(payload: dict[str, object], field: str) -> dict[str, object]:
    result = dict(payload)
    result[field] = canonical_hash(result)
    return result


def _gate(evidence_root: Path, index: int) -> Path:
    gate_name = cast("GateName", f"Q{index}")
    gate_path = _write(
        evidence_root / "personal-workstation" / "gates" / f"{gate_name}.json",
        {
            "schema_version": 1,
            "gate": gate_name,
            "gate_status": "passed",
            "engineering_status": "PROVEN",
            "evidence": [],
            "blockers": [],
        },
    )
    write_gate_manifest(
        evidence_root / "personal-workstation" / "manifests" / f"{gate_name}.json",
        build_gate_manifest(evidence_root, gate_name, (gate_path,)),
    )
    return gate_path


def _paths(tmp_path: Path) -> ReleaseCandidateArtifactPaths:
    proposal_arguments = {
        "operation": "run-accelerated-real-provider-paper-acceptance-v1",
        "acceptance": {
            "mode": "accelerated_real_provider_replay",
            "qualifies_as_wall_clock_soak": False,
            "qualifies_as_release_acceptance": True,
            "requires_current_live_day_anchor": True,
        },
        "live_day_anchor": {
            "approval_hash": "a" * 64,
            "day_evidence_hash": "b" * 64,
        },
        "replay": {"trade_dates": [f"2026-08-{day:02d}" for day in range(1, 21)]},
    }
    approval_hash = canonical_hash(proposal_arguments)
    proposal = {
        "schema": "ditto.q4-accelerated-paper-acceptance-proposal.v1",
        "exact_acceptance_request": {
            "approval_hash": approval_hash,
            "arguments": proposal_arguments,
        },
    }
    bootstrap = {
        "schema": "ditto.pap09-accelerated-provider-replay-bootstrap.v1",
        "status": "passed",
        "request_hash": approval_hash,
        "acceptance_mode": "accelerated_real_provider_replay",
        "qualifies_as_wall_clock_soak": False,
        "qualifies_as_release_acceptance": True,
        "live_day_anchor": {
            "approval_hash": "a" * 64,
            "day_evidence_hash": "b" * 64,
        },
        "safety": {"paper_only": True, "broker_connections": 0, "real_orders": 0},
    }
    progress = {
        "schema": "ditto.pap09-accelerated-provider-replay.v1",
        "status": "passed",
        "approval_hash": approval_hash,
        "acceptance_mode": "accelerated_real_provider_replay",
        "qualifies_as_wall_clock_soak": False,
        "qualifies_as_release_acceptance": True,
        "accelerated_trading_day_count": 20,
        "trade_dates": [f"2026-08-{day:02d}" for day in range(1, 21)],
        "day_evidence_hashes": [
            hashlib.sha256(str(day).encode()).hexdigest() for day in range(20)
        ],
        "daily_reconciliations_balanced": [True] * 20,
        "signature_chain_valid": True,
        "q4_five_day_ready": True,
        "pap09_twenty_day_release_ready": True,
        "remaining_accelerated_trading_days": 0,
        "safety": {"paper_only": True, "broker_connections": 0, "real_orders": 0},
    }
    restore = {
        "schema": "ditto.q1-backup-restore.v2",
        "status": "passed",
        "passed": True,
        "payload_tree": {"hashes_equal": True},
        "sqlite": {
            "backup_integrity_check": "ok",
            "restore_integrity_check": "ok",
            "source_integrity_check": "ok",
            "logical_row_counts_equal": True,
        },
        "verification": {
            "backup_preserved": True,
            "non_overwriting_backup": True,
            "non_overwriting_restore": True,
            "restore_preserved": True,
            "source_preserved": True,
        },
    }
    q5_snapshot_id = "snapshot:tushare:etf_daily:sha256:" + "c" * 64
    q5_payload_checksum = "d" * 32
    q5_spec_hash = "e" * 64
    q5_artifact_id = "signal-package-seed-etf"
    q5_arguments = {
        "operation": "close-live-model-paper-manual-portfolio-v1",
        "strategy": {
            "strategy_id": "seed_etf_industry_rotation",
            "strategy_version": 1,
            "spec_hash": q5_spec_hash,
        },
        "decision": {
            "signal_date": "2026-09-02",
            "account_id": "manual-q4-owner-acceptance",
            "paper_account_id": "paper-pap09-owner-acceptance",
            "paper_session_id": "pap09-session-2026-09-02",
        },
        "provider": {
            "snapshot_id": q5_snapshot_id,
            "payload_checksum": q5_payload_checksum,
        },
    }
    q5_approval_hash = canonical_hash(q5_arguments)
    q5_proposal = {
        "schema": "ditto.q5-live-portfolio-acceptance-proposal.v1",
        "status": "pending_operator_approval",
        "exact_acceptance_request": {
            "arguments": q5_arguments,
            "approval_hash": q5_approval_hash,
            "requires_exact_approval": True,
        },
    }
    q5 = _self_hashed(
        {
            "schema": "ditto.q5-live-portfolio-acceptance.v1",
            "generated_at": "2026-09-02T13:00:00Z",
            "status": "passed",
            "passed": True,
            "request_hash": q5_approval_hash,
            "provider": {
                "snapshot_id": q5_snapshot_id,
                "payload_checksum": q5_payload_checksum,
            },
            "strategy_run": {
                "strategy_id": "seed_etf_industry_rotation",
                "strategy_version": 1,
                "spec_hash": q5_spec_hash,
            },
            "signal_package": {"artifact_id": q5_artifact_id},
            "comparison_request": {
                "strategy_id": "seed_etf_industry_rotation",
                "model_portfolio_id": q5_artifact_id,
                "paper_account_id": "paper-pap09-owner-acceptance",
                "manual_account_id": "manual-q4-owner-acceptance",
                "paper_session_id": "pap09-session-2026-09-02",
                "as_of": "2026-09-02",
                "source_snapshot_ids": [q5_snapshot_id],
            },
            "safety": {
                "broker_connections": 0,
                "real_orders": 0,
                "paper_or_manual_journal_mutations": 0,
                "strategy_governance_mutations": 0,
                "agent_write_tools": 0,
            },
        },
        "evidence_hash",
    )
    diagnostic = _self_hashed(
        {
            "schema": "ditto.q5-live-portfolio-diagnostic.v1",
            "generated_at": "2026-09-02T13:10:00Z",
            "status": "passed",
            "passed": True,
            "provider": "glm",
            "q5_acceptance_hash": q5["evidence_hash"],
            "run": {
                "status": "completed",
                "guardrail_status": "passed",
                "usage": {"tool_calls": 1},
                "episode_verified": True,
            },
            "egress": {"license_class": "approved-research"},
            "safety": {
                "broker_connections": 0,
                "real_orders": 0,
                "account_or_target_mutations": 0,
                "agent_write_tools": 0,
            },
        },
        "report_hash",
    )
    ui08 = _self_hashed(
        {
            "schema": "ditto.personal-workstation.ui08-final.v1",
            "generated_at": "2026-09-02T13:20:00Z",
            "status": "passed",
            "passed": True,
            "steps": [{"step": step, "state": "passed"} for step in range(1, 11)],
            "browser": {
                "mock_enabled": False,
                "live_backend": True,
                "console_error_count": 0,
            },
            "evidence_bindings": {
                "q5_acceptance_hash": q5["evidence_hash"],
                "portfolio_diagnostic_hash": diagnostic["report_hash"],
            },
            "safety": {"broker_connections": 0, "real_orders": 0},
        },
        "report_hash",
    )
    backend = {
        "schema_version": 1,
        "captured_at": "2026-09-02T13:31:00Z",
        "full_ci": {
            "status": "passed",
            "completed_at": "2026-09-02T13:30:00Z",
        },
        "pit_gate": {"status": "passed"},
        "post_pap09_changed_scope": {"status": "passed"},
        "diff_check": {"status": "passed"},
    }
    frontend = {
        "schema_version": 1,
        "captured_at": "2026-09-02T13:31:00Z",
        "full_ci": {
            "status": "passed",
            "completed_at": "2026-09-02T13:30:00Z",
        },
        "openapi_zero_diff": {"status": "passed"},
        "ui_07": {"status": "passed"},
        "diff_check": {"status": "passed"},
    }
    gates = tuple(_gate(tmp_path, index) for index in range(6))
    return ReleaseCandidateArtifactPaths(
        accelerated_proposal=_write(tmp_path / "proposal.json", proposal),
        accelerated_bootstrap=_write(tmp_path / "bootstrap.json", bootstrap),
        accelerated_progress=_write(tmp_path / "progress.json", progress),
        restore_evidence=_write(tmp_path / "restore.json", restore),
        q5_proposal=_write(tmp_path / "q5-proposal.json", q5_proposal),
        q5_acceptance=_write(tmp_path / "q5.json", q5),
        portfolio_diagnostic=_write(tmp_path / "diagnostic.json", diagnostic),
        ui08_final=_write(tmp_path / "ui08.json", ui08),
        backend_validation=_write(tmp_path / "backend.json", backend),
        frontend_validation=_write(tmp_path / "frontend.json", frontend),
        prerequisite_gates=gates,
    )


def test_release_candidate_bundle_closes_ops10_without_claiming_wall_clock(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    result = build_release_candidate_bundle(
        paths,
        generated_at=datetime(2026, 9, 2, 14, tzinfo=UTC),
    )

    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["work_package"] == "OPS-10"
    assert result["qualifies_as_wall_clock_soak"] is False
    assert result["accelerated_trading_day_count"] == 20
    assert result["fresh_bootstrap"] is True
    assert result["restore_verified"] is True
    assert result["ui08_steps_passed"] == 10
    assert result["prerequisite_gates"] == [f"Q{index}" for index in range(6)]
    assert result["q5_acceptance_approval_hash"] == canonical_hash(
        q5_arguments := orjson.loads(paths.q5_proposal.read_bytes())[
            "exact_acceptance_request"
        ]["arguments"]
    )
    assert q5_arguments["operation"] == "close-live-model-paper-manual-portfolio-v1"
    assert len(cast("list[object]", result["artifacts"])) == 22
    body = {key: value for key, value in result.items() if key != "bundle_hash"}
    assert result["bundle_hash"] == canonical_hash(body)


def test_release_candidate_bundle_fails_closed_on_partial_accelerated_or_ui_state(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    progress = orjson.loads(paths.accelerated_progress.read_bytes())
    progress["accelerated_trading_day_count"] = 19
    _write(paths.accelerated_progress, progress)

    with pytest.raises(ValueError, match="accelerated acceptance"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))

    paths = _paths(tmp_path / "ui")
    ui08 = orjson.loads(paths.ui08_final.read_bytes())
    ui08["steps"][-1]["state"] = "pending"
    _write(paths.ui08_final, ui08)

    with pytest.raises(ValueError, match="UI-08"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_rejects_accelerated_trade_date_identity_drift(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    progress = orjson.loads(paths.accelerated_progress.read_bytes())
    progress["trade_dates"] = [f"2026-07-{day:02d}" for day in range(1, 21)]
    _write(paths.accelerated_progress, progress)

    with pytest.raises(ValueError, match="accelerated acceptance"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_rejects_ui08_evidence_binding_drift(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    ui08 = orjson.loads(paths.ui08_final.read_bytes())
    ui08["evidence_bindings"]["q5_acceptance_hash"] = "f" * 64
    ui08.pop("report_hash")
    ui08["report_hash"] = canonical_hash(ui08)
    _write(paths.ui08_final, ui08)

    with pytest.raises(ValueError, match="UI-08"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_requires_q5_approval_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    q5 = orjson.loads(paths.q5_acceptance.read_bytes())
    q5["request_hash"] = "f" * 64
    q5.pop("evidence_hash")
    q5["evidence_hash"] = canonical_hash(q5)
    _write(paths.q5_acceptance, q5)

    with pytest.raises(ValueError, match="Q5 approval"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_requires_diagnostic_q5_binding(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    diagnostic = orjson.loads(paths.portfolio_diagnostic.read_bytes())
    diagnostic["q5_acceptance_hash"] = "f" * 64
    diagnostic.pop("report_hash")
    diagnostic["report_hash"] = canonical_hash(diagnostic)
    _write(paths.portfolio_diagnostic, diagnostic)
    ui08 = orjson.loads(paths.ui08_final.read_bytes())
    ui08["evidence_bindings"]["portfolio_diagnostic_hash"] = diagnostic["report_hash"]
    ui08.pop("report_hash")
    ui08["report_hash"] = canonical_hash(ui08)
    _write(paths.ui08_final, ui08)

    with pytest.raises(ValueError, match="PortfolioDiagnostic"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_rejects_ci_completed_before_final_evidence(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    backend = orjson.loads(paths.backend_validation.read_bytes())
    backend["full_ci"]["completed_at"] = "2026-09-02T13:19:59Z"
    _write(paths.backend_validation, backend)

    with pytest.raises(ValueError, match="final evidence"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))


def test_release_candidate_bundle_rejects_generation_before_validation_capture(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    with pytest.raises(ValueError, match="bundle generation"):
        build_release_candidate_bundle(
            paths,
            generated_at=datetime(2026, 9, 2, 13, 30, 59, tzinfo=UTC),
        )


def test_release_candidate_bundle_requires_authenticated_gate_manifests(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    missing_manifest = (
        paths.prerequisite_gates[0].parent.parent
        / "manifests"
        / paths.prerequisite_gates[0].name
    )
    missing_manifest.unlink()

    with pytest.raises(ValueError, match="Gate manifest"):
        build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))
