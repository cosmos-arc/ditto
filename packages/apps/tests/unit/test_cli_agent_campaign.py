"""Contract tests for the governed Agent Campaign CLI group."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_application.agent_campaign_runtime import (
    CampaignApproveCommand,
    CampaignBudgetView,
    CampaignCancelCommand,
    CampaignCreateCommand,
    CampaignRuntimePort,
    CampaignSandboxBudgetView,
    CampaignStatus,
    CampaignView,
)
from ditto_apps.cli.commands import agent
from ditto_apps.cli.main import app as main_app
from typer.testing import CliRunner

NOW = datetime(2026, 8, 16, 7, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def _view(
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> CampaignView:
    authorized = status is not CampaignStatus.DRAFT
    return CampaignView(
        campaign_id="campaign-cli",
        status=status,
        manifest_hash=HASH_A,
        authorization_hash=HASH_B if authorized else None,
        authorized_by="operator-cli" if authorized else None,
        authorization_expires_at=(NOW + timedelta(hours=4) if authorized else None),
        search_axis="factor_code",
        source_snapshot_id="snapshot-cli",
        allowed_tools=("campaign_propose_candidate",),
        budget=CampaignBudgetView(
            candidate_limit=8,
            fold_run_limit=16,
            generation_limit=6,
            concurrent_sandbox_limit=2,
            wall_time_limit_seconds=14_400,
            temporary_storage_limit_bytes=20 * 1024**3,
            model_spend_limit_usd_micros=8_000_000,
            sandbox_resource_limits=CampaignSandboxBudgetView(
                cpu_count=2,
                memory_bytes=4 * 1024**3,
                process_limit=64,
                temporary_storage_bytes=1024**3,
                wall_time_seconds=600,
                output_bytes=10 * 1024**2,
            ),
        ),
        best_primary_metric_value=None,
        no_improvement_generations=0,
        statistical_trial_count=0,
        operational_attempt_count=0,
        revision=1 if authorized else 0,
        canonical_manifest={"campaign_id": "campaign-cli"},
    )


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: MagicMock,
) -> MagicMock:
    container = MagicMock()
    container.get.return_value = runtime
    monkeypatch.setattr(agent, "make_app_container", MagicMock(return_value=container))
    return container


def test_campaign_help_registers_fixed_r53_surface() -> None:
    runner = CliRunner()

    result = runner.invoke(main_app, ["agent", "campaign", "--help"])

    assert result.exit_code == 0, result.output
    for command in ("create", "approve", "show", "cancel"):
        assert command in result.stdout


def test_campaign_create_reads_manifest_and_calls_shared_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runtime = MagicMock(spec=CampaignRuntimePort)
    runtime.create_campaign.return_value = _view()
    container = _install_runtime(monkeypatch, runtime)
    manifest = tmp_path / "campaign.json"
    manifest.write_bytes(
        orjson.dumps(
            {
                "campaign_id": "campaign-cli",
                "objective": "A local governed research objective.",
            }
        )
    )

    result = CliRunner().invoke(
        main_app,
        [
            "agent",
            "campaign",
            "create",
            str(manifest),
            "--idempotency-key",
            "campaign-create-cli",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    command = runtime.create_campaign.call_args.args[0]
    assert isinstance(command, CampaignCreateCommand)
    assert command.manifest_document["campaign_id"] == "campaign-cli"
    assert command.idempotency_key == "campaign-create-cli"
    assert orjson.loads(result.stdout)["manifest_hash"] == HASH_A
    container.get.assert_called_once_with(CampaignRuntimePort)
    container.close.assert_called_once_with()


def test_campaign_approve_show_and_cancel_use_exact_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock(spec=CampaignRuntimePort)
    runtime.approve_campaign.return_value = _view(status=CampaignStatus.AUTHORIZED)
    runtime.get_campaign.return_value = _view(status=CampaignStatus.AUTHORIZED)
    runtime.cancel_campaign.return_value = _view(status=CampaignStatus.CANCELLED)
    _install_runtime(monkeypatch, runtime)
    runner = CliRunner()

    approved = runner.invoke(
        main_app,
        [
            "agent",
            "campaign",
            "approve",
            "campaign-cli",
            "--expected-manifest-hash",
            HASH_A,
            "--operator-id",
            "operator-cli",
            "--expires-at",
            (NOW + timedelta(hours=4)).isoformat(),
            "--idempotency-key",
            "campaign-approve-cli",
            "--json",
        ],
    )
    shown = runner.invoke(
        main_app,
        ["agent", "campaign", "show", "campaign-cli", "--json"],
    )
    cancelled = runner.invoke(
        main_app,
        [
            "agent",
            "campaign",
            "cancel",
            "campaign-cli",
            "--expected-authorization-hash",
            HASH_B,
            "--idempotency-key",
            "campaign-cancel-cli",
            "--json",
        ],
    )

    assert approved.exit_code == shown.exit_code == cancelled.exit_code == 0
    approve_command = runtime.approve_campaign.call_args.args[0]
    assert isinstance(approve_command, CampaignApproveCommand)
    assert approve_command.expected_manifest_hash == HASH_A
    assert approve_command.operator_id == "operator-cli"
    cancel_command = runtime.cancel_campaign.call_args.args[0]
    assert isinstance(cancel_command, CampaignCancelCommand)
    assert cancel_command.expected_authorization_hash == HASH_B
    assert runtime.get_campaign.call_args.args == ("campaign-cli",)
    assert orjson.loads(cancelled.stdout)["status"] == "cancelled"
