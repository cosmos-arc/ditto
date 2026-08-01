"""Contracts for the deterministic R3 research acceptance runner."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import orjson
from ditto_apps.scripts.r3_research_acceptance import (
    CommandResult,
    deterministic_commands,
    run_fixture_acceptance,
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
