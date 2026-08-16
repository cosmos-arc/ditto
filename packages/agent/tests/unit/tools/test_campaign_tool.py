"""Campaign-scoped candidate proposal tool boundary tests."""

from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import ditto_agent.tools.campaign as campaign_module
import pytest
from ditto_agent.contracts.approval import (
    CampaignAuthorization,
    CampaignBudget,
    CampaignGrant,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.campaign import (
    CampaignProposalTool,
    CampaignToolExecutionContext,
)
from ditto_application.agent_campaign_contracts import (
    AutonomousCampaignCommandPort,
    CampaignCandidateProposalCommand,
    CampaignCandidateReceipt,
)

NOW = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _authorization() -> CampaignAuthorization:
    return CampaignAuthorization.issue(
        authorization_id="campaign-auth-001",
        grant=CampaignGrant(
            campaign_manifest_hash="a" * 64,
            authority_hash="b" * 64,
            authorized_by="operator-001",
            authorized_at=NOW,
            expires_at=NOW + timedelta(hours=4),
            search_axis="factor_code",
            allowed_tools=("campaign_propose_candidate",),
            source_snapshot_id="snapshot-2026-08-12",
            budget=CampaignBudget(
                max_generations=6,
                max_unique_candidates=8,
                max_fold_runs=16,
                max_concurrent_sandboxes=2,
                max_wall_time_seconds=14_400,
                max_temporary_storage_bytes=20 * 1024**3,
                max_model_spend_usd=Decimal("8"),
            ),
        ),
    )


def _context(
    authorization: CampaignAuthorization,
    *,
    decision_time: datetime = NOW + timedelta(minutes=1),
    authority_hash: str | None = None,
) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=NOW,
            publication_cutoff=NOW,
            source_snapshot_id=authorization.source_snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
            campaign_authorization_id=authorization.authorization_id,
            campaign_authority_hash=(
                authorization.authority_hash
                if authority_hash is None
                else authority_hash
            ),
        )
    )


class _Commands:
    def __init__(self) -> None:
        self.calls: list[CampaignCandidateProposalCommand] = []

    def propose_candidate(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        occurred_at: datetime,
    ) -> CampaignCandidateReceipt:
        self.calls.append(command)
        return CampaignCandidateReceipt.issue(
            command=command,
            candidate_id="candidate-proposed",
            candidate_hash="c" * 64,
            generation=1,
            status="running",
            event_id="campaign-event-proposed",
            occurred_at=occurred_at,
        )


def _tool(commands: _Commands) -> CampaignProposalTool:
    return CampaignProposalTool(commands=cast(AutonomousCampaignCommandPort, commands))


def _execution() -> CampaignToolExecutionContext:
    return CampaignToolExecutionContext(
        campaign_id="campaign-autonomous",
        run_id="run-campaign-001",
        episode_id="episode-run-campaign-001",
        call_id="call-campaign-001",
    )


def test_campaign_tool_schema_exposes_only_candidate_proposal_fields() -> None:
    spec = _tool(_Commands()).spec

    assert spec.name == "campaign_propose_candidate"
    assert not spec.requires_approval
    assert set(spec.input_schema["properties"]) == {
        "parent_candidate_id",
        "parameters",
        "factor_code_hash",
        "model_code_hash",
        "data_requirement_hashes",
    }
    forbidden = {
        "authorization_id",
        "authorization_hash",
        "authority_hash",
        "campaign_id",
        "search_axis",
        "generation",
        "holdout",
        "publish",
        "order",
        "broker",
    }
    assert forbidden.isdisjoint(spec.input_schema["properties"])


def test_tool_injects_campaign_authority_and_seals_application_receipt() -> None:
    commands = _Commands()
    authorization = _authorization()
    envelope = _tool(commands).invoke(
        arguments={
            "parent_candidate_id": "candidate-baseline",
            "parameters": {"lookback": 10},
            "factor_code_hash": "d" * 64,
            "model_code_hash": None,
            "data_requirement_hashes": ["e" * 64],
        },
        context=_context(authorization),
        authorization=authorization,
        execution=_execution(),
    )

    command = commands.calls[0]
    assert command.campaign_id == "campaign-autonomous"
    assert command.authorization_id == authorization.authorization_id
    assert command.authorization_hash == authorization.authorization_hash
    assert command.authority_hash == authorization.authority_hash
    assert command.run_id == "run-campaign-001"
    assert command.call_id == "call-campaign-001"
    assert envelope.result["receipt"]["candidate_id"] == "candidate-proposed"
    assert envelope.verify_integrity()


@pytest.mark.parametrize("failure", ["tampered", "expired", "context"])
def test_tool_fails_closed_before_application_on_authority_failure(
    failure: str,
) -> None:
    commands = _Commands()
    authorization = _authorization()
    context = _context(authorization)
    if failure == "tampered":
        authorization = replace(authorization, authorization_hash="0" * 64)
    elif failure == "expired":
        context = _context(
            authorization,
            decision_time=authorization.expires_at + timedelta(seconds=1),
        )
    else:
        context = _context(authorization, authority_hash="f" * 64)

    with pytest.raises(ValueError):
        _tool(commands).invoke(
            arguments={
                "parent_candidate_id": "candidate-baseline",
                "parameters": {"lookback": 10},
                "factor_code_hash": "d" * 64,
                "model_code_hash": None,
                "data_requirement_hashes": ["e" * 64],
            },
            context=context,
            authorization=authorization,
            execution=_execution(),
        )

    assert commands.calls == []


def test_campaign_tool_has_no_analysis_or_physical_store_dependency() -> None:
    source = inspect.getsource(campaign_module)

    assert "ditto_application.agent_campaign_contracts" in source
    assert "ditto_analysis" not in source
    assert "storage.sqlite" not in source
