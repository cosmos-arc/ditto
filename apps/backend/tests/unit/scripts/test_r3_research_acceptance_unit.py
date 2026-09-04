"""Contracts for the deterministic R3 research acceptance runner."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import ditto_apps.scripts.r3_research_acceptance as acceptance
import orjson
import pytest
from ditto_apps.scripts.r3_research_acceptance import (
    CommandResult,
    deterministic_commands,
    run_fixture_acceptance,
)
from packages.application.tests.integration.r2_live_gate_binding_support import (
    ready_source,
)


def _passing_runner(
    name: str,
    command: Sequence[str],
    cwd: Path,
) -> CommandResult:
    return CommandResult.from_capture(
        name=name,
        command=tuple(command),
        returncode=0,
        stdout=f"{name}: passed in {cwd.name}",
        stderr="",
    )


def test_fixture_report_is_engineering_pass_but_release_blocked(
    tmp_path: Path,
) -> None:
    output = tmp_path / "artifacts" / "r3-report.json"
    manifest = tmp_path / "evidence" / "manifest.json"
    report = run_fixture_acceptance(
        workspace_root=tmp_path,
        output=output,
        manifest=manifest,
        checked_at=datetime(2026, 8, 1, 1, 2, 3, tzinfo=UTC),
        source_commit="a" * 40,
        command_runner=_passing_runner,
    )

    payload = orjson.loads(output.read_bytes())
    assert report.passed is True
    assert payload["mode"] == "deterministic_fixture"
    assert payload["release_status"] == "RELEASE_ACCEPTANCE_BLOCKED"
    assert payload["r2_live_gate"] == "NOT_EVALUATED"
    assert payload["golden_lanes"] == ["stock", "etf"]
    assert payload["gate_evidence"] == {
        "publish_promotion": {
            "active_pointer_unchanged": True,
            "append_only_event_count_unchanged": True,
            "called": True,
            "expected_error_code": "hard_gate_blocked",
            "zero_write": True,
        },
        "submit_review": {
            "active_pointer_unchanged": True,
            "append_only_event_count_unchanged": True,
            "called": True,
            "expected_error_code": "HARD_GATE_FAILED",
            "zero_write": True,
        },
    }
    assert payload["does_not_prove"] == [
        "provider_entitlement",
        "certified_live_data",
        "live_96_month_history",
        "real_browser_acceptance",
        "production_recovery",
    ]
    assert all(
        item["artifact_hashes"]["command_transcript"] for item in payload["commands"]
    )
    assert manifest.is_file()

    serialized = output.read_text(encoding="utf-8")
    assert '"live_passed": true' not in serialized
    assert '"release_status": "RELEASE_ACCEPTANCE_PASSED"' not in serialized
    assert "production drill" not in serialized.lower()


def test_runner_executes_every_required_acceptance_seam() -> None:
    commands = deterministic_commands()
    by_name = {item.name: item for item in commands}

    assert tuple(by_name) == (
        "backend-check",
        "stock-golden",
        "etf-golden",
        "governance-recovery",
        "hard-gate-zero-write",
        "scheduler-literal-128",
        "isolated-backup-restore",
        "openapi-zero-diff",
    )
    assert "test_r3_stock_selection_golden.py" in " ".join(
        by_name["stock-golden"].command
    )
    assert "test_r3_etf_research_golden.py" in " ".join(by_name["etf-golden"].command)
    assert "test_r3_scheduler_capacity.py" in " ".join(
        by_name["scheduler-literal-128"].command
    )
    assert "test_fixture_hard_gate_paths_are_zero_write" in " ".join(
        by_name["hard-gate-zero-write"].command
    )
    assert "test_fixture_backup_restore_preserves_domain_identity" in " ".join(
        by_name["isolated-backup-restore"].command
    )
    assert "test_static_openapi_matches_canonical_runtime_contract" in " ".join(
        by_name["openapi-zero-diff"].command
    )


def test_fixture_runner_rejects_relative_workspace_root(tmp_path: Path) -> None:
    """The engineering seam must never fall back to process-CWD semantics."""
    with pytest.raises(ValueError, match="workspace_root must be an absolute path"):
        run_fixture_acceptance(
            workspace_root=Path("relative-workspace"),
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "manifest.json",
            source_commit="a" * 40,
            command_runner=_passing_runner,
        )


def test_any_failed_command_fails_engineering_acceptance_but_not_release_truth(
    tmp_path: Path,
) -> None:
    def failing_runner(
        name: str,
        command: Sequence[str],
        cwd: Path,
    ) -> CommandResult:
        del cwd
        return CommandResult.from_capture(
            name=name,
            command=tuple(command),
            returncode=7 if name == "etf-golden" else 0,
            stdout="",
            stderr="fixture failure" if name == "etf-golden" else "",
        )

    report = run_fixture_acceptance(
        workspace_root=tmp_path,
        output=tmp_path / "r3-report.json",
        manifest=tmp_path / "manifest.json",
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="b" * 40,
        command_runner=failing_runner,
    )

    assert report.passed is False
    assert report.release_status == "RELEASE_ACCEPTANCE_BLOCKED"
    assert report.r2_live_gate == "NOT_EVALUATED"
    assert report.failures == ("etf-golden",)


def _write_r2_source_manifest(root: Path) -> tuple[Path, Path]:
    source = ready_source(root)
    manifest = root / "r2-report.manifest.json"

    def entry(path: Path, content_hash: str) -> dict[str, str]:
        return {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": content_hash,
        }

    manifest.write_bytes(
        orjson.dumps(
            {
                "schema": "ditto.r2-live-gate-source",
                "version": 1,
                "report": entry(source.report_path, source.expected_report_hash),
                "groups": {
                    "provider_entitlement": [
                        entry(item.path, item.expected_content_hash)
                        for item in source.provider_entitlement_artifacts
                    ],
                    "performance": [
                        entry(item.path, item.expected_content_hash)
                        for item in source.performance_artifacts
                    ],
                    "recoverability": [
                        entry(item.path, item.expected_content_hash)
                        for item in source.recoverability_artifacts
                    ],
                    "idempotency": [
                        entry(item.path, item.expected_content_hash)
                        for item in source.idempotency_artifacts
                    ],
                },
            },
            option=orjson.OPT_SORT_KEYS,
        )
    )
    return source.report_path, manifest


def test_live_cli_requires_exact_mode_and_release_guards(tmp_path: Path) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)
    args = acceptance._parser().parse_args(
        [
            "--real-data",
            "--workspace-root",
            str(tmp_path),
            "--require-certified",
            "--require-both-golden-lanes",
            "--r2-evidence",
            str(report),
            "--r2-source-manifest",
            str(source_manifest),
            "--output",
            str(tmp_path / "r3-report.json"),
        ]
    )

    assert args.real_data is True
    assert args.fixture is False
    assert args.workspace_root == tmp_path
    assert args.require_certified is True
    assert args.require_both_golden_lanes is True
    assert args.r2_evidence == report
    assert args.r2_source_manifest == source_manifest

    with pytest.raises(SystemExit):
        acceptance._parser().parse_args(
            [
                "--fixture",
                "--real-data",
                "--workspace-root",
                str(tmp_path),
            ]
        )


def test_live_runner_without_explicit_environment_opt_in_is_blocked(
    tmp_path: Path,
) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)

    def unexpected_runner(
        name: str,
        command: Sequence[str],
        cwd: Path,
    ) -> CommandResult:
        pytest.fail(f"live command unexpectedly ran: {name} {command} {cwd}")

    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="c" * 40,
        command_runner=unexpected_runner,
    )

    assert result.passed is False
    assert result.release_status == "RELEASE_ACCEPTANCE_BLOCKED"
    assert result.r2_live_gate == "NOT_EVALUATED"
    assert result.failures == ("real_data_opt_in_missing",)
    assert result.commands == ()


def test_content_verified_ready_r2_source_runs_live_command_contract(
    tmp_path: Path,
) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)
    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={"DITTO_RUN_REAL_DATA_ACCEPTANCE": "1"},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="d" * 40,
        command_runner=_passing_runner,
    )

    assert result.passed is True
    assert result.release_status == "RELEASE_ACCEPTANCE_PASSED"
    assert result.r2_live_gate == "PASS"
    assert result.golden_lanes == ("stock", "etf")
    assert result.failures == ()
    assert tuple(item.name for item in result.commands) == (
        "stock-live-golden",
        "etf-live-golden",
        "governance-live-lifecycle",
        "isolated-live-backup-restore",
    )
    payload = orjson.loads((tmp_path / "r3-report.json").read_bytes())
    assert payload["mode"] == "real_data"
    assert payload["r2_evidence"]["report_hash"]
    assert payload["r2_evidence"]["status"] == "ready"
    manifest = orjson.loads((tmp_path / "r3-manifest.json").read_bytes())
    assert manifest["entries"][0]["mode"] == "live"


def test_live_runner_binds_verified_r2_source_only_while_commands_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)
    monkeypatch.setenv("DITTO_R2_LIVE_REPORT_PATH", "previous-report")
    monkeypatch.setenv(
        "DITTO_R2_LIVE_SOURCE_MANIFEST_PATH",
        "previous-source-manifest",
    )
    observed: list[tuple[str, str]] = []

    def source_asserting_runner(
        name: str,
        command: Sequence[str],
        cwd: Path,
    ) -> CommandResult:
        del cwd
        observed.append(
            (
                os.environ["DITTO_R2_LIVE_REPORT_PATH"],
                os.environ["DITTO_R2_LIVE_SOURCE_MANIFEST_PATH"],
            )
        )
        return CommandResult.from_capture(
            name=name,
            command=tuple(command),
            returncode=0,
            stdout="verified R2 source was visible",
            stderr="",
        )

    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={"DITTO_RUN_REAL_DATA_ACCEPTANCE": "1"},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="d" * 40,
        command_runner=source_asserting_runner,
    )

    assert result.passed is True
    assert observed == [(str(report.resolve()), str(source_manifest.resolve()))] * len(
        acceptance.live_commands()
    )
    assert os.environ["DITTO_R2_LIVE_REPORT_PATH"] == "previous-report"
    assert (
        os.environ["DITTO_R2_LIVE_SOURCE_MANIFEST_PATH"] == "previous-source-manifest"
    )


def test_live_runner_does_not_execute_when_r2_manifest_hash_drifts(
    tmp_path: Path,
) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)
    report.write_bytes(b"{}")

    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={"DITTO_RUN_REAL_DATA_ACCEPTANCE": "1"},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="e" * 40,
        command_runner=lambda *_: pytest.fail("must fail before live commands"),
    )

    assert result.release_status == "RELEASE_ACCEPTANCE_BLOCKED"
    assert result.r2_live_gate == "NOT_EVALUATED"
    assert result.failures == ("r2_live_evidence_unverified",)
    assert result.commands == ()


def test_live_runner_fails_release_when_one_live_command_fails(
    tmp_path: Path,
) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)

    def failing_live_runner(
        name: str,
        command: Sequence[str],
        cwd: Path,
    ) -> CommandResult:
        del cwd
        return CommandResult.from_capture(
            name=name,
            command=tuple(command),
            returncode=9 if name == "etf-live-golden" else 0,
            stdout="",
            stderr="live failure" if name == "etf-live-golden" else "",
        )

    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={"DITTO_RUN_REAL_DATA_ACCEPTANCE": "1"},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="f" * 40,
        command_runner=failing_live_runner,
    )

    assert result.passed is False
    assert result.release_status == "RELEASE_ACCEPTANCE_BLOCKED"
    assert result.r2_live_gate == "PASS"
    assert result.failures == ("etf-live-golden",)


def test_r2_source_manifest_rejects_parent_path_escape(tmp_path: Path) -> None:
    report, source_manifest = _write_r2_source_manifest(tmp_path)
    payload = orjson.loads(source_manifest.read_bytes())
    payload["report"]["relative_path"] = "../outside.json"
    source_manifest.write_bytes(orjson.dumps(payload))

    result = acceptance.run_live_acceptance(
        request=acceptance.LiveAcceptanceRequest(
            workspace_root=tmp_path,
            output=tmp_path / "r3-report.json",
            manifest=tmp_path / "r3-manifest.json",
            r2_evidence=report,
            r2_source_manifest=source_manifest,
            require_certified=True,
            require_both_golden_lanes=True,
        ),
        environment={"DITTO_RUN_REAL_DATA_ACCEPTANCE": "1"},
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_commit="1" * 40,
        command_runner=lambda *_: pytest.fail("must fail before live commands"),
    )

    assert result.failures == ("r2_live_evidence_unverified",)
