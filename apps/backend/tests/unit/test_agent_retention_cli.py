from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_agent.retention import RetentionExecutionResult, RetentionPlan
from ditto_apps.cli.commands import agent_retention
from ditto_apps.cli.main import app as main_app
from typer.testing import CliRunner

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)


def _plan() -> RetentionPlan:
    return RetentionPlan.create(
        as_of=NOW,
        cutoff=NOW - timedelta(days=30),
        candidates=(),
    )


def _install_service(
    monkeypatch: pytest.MonkeyPatch,
    service: MagicMock,
) -> None:
    @contextmanager
    def factory(data_root: Path | None) -> Generator[MagicMock]:
        del data_root
        yield service

    monkeypatch.setattr(agent_retention, "_retention_service", factory)


def test_retention_cleanup_defaults_to_auditable_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan()
    service = MagicMock()
    service.dry_run.return_value = plan
    _install_service(monkeypatch, service)

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "retention-cleanup",
            "--data-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = orjson.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["plan_hash"] == plan.plan_hash
    assert payload["candidate_count"] == 0
    service.execute.assert_not_called()


def test_retention_cleanup_execute_requires_hash_and_external_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan()
    service = MagicMock()
    service.dry_run.return_value = plan
    service.execute.return_value = RetentionExecutionResult(
        plan_hash=plan.plan_hash,
        approval_id="approval-retention-r5",
        deleted_target_ids=(),
        audit_payload_hash="a" * 64,
        executed_at=NOW,
    )
    _install_service(monkeypatch, service)

    missing = CliRunner().invoke(
        main_app,
        [
            "agent",
            "retention-cleanup",
            "--data-root",
            str(tmp_path),
            "--execute",
            "--json",
        ],
    )
    assert missing.exit_code == 2
    service.execute.assert_not_called()

    executed = CliRunner().invoke(
        main_app,
        [
            "agent",
            "retention-cleanup",
            "--data-root",
            str(tmp_path),
            "--execute",
            "--expected-plan-hash",
            plan.plan_hash,
            "--approval-id",
            "approval-retention-r5",
            "--json",
        ],
    )

    assert executed.exit_code == 0, executed.output
    payload = orjson.loads(executed.stdout)
    assert payload["mode"] == "execute"
    assert payload["approval_id"] == "approval-retention-r5"
    assert payload["deleted_target_ids"] == []
    assert service.execute.call_args.kwargs["expected_plan_hash"] == plan.plan_hash
    assert service.execute.call_args.kwargs["approval_id"] == "approval-retention-r5"
