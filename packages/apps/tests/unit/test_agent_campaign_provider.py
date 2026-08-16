"""Composition-root wiring for the Campaign proposal tool."""

from typing import cast

import pytest
from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_agent.tools.memory import ResearchMemoryTool
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_application.agent_campaign_runtime import (
    CampaignCreateCommand,
    CampaignRuntimeUnavailable,
)
from ditto_application.exceptions import AppCommandError
from ditto_application.queries.research_memory import ResearchMemoryQueryFacade
from ditto_application.research_memory_approval_contracts import (
    ResearchMemoryApprovalCheck,
)
from ditto_apps.registry.agent.provider import AgentRuntimeProvider


class _Commands:
    pass


def test_apps_provider_wires_campaign_proposal_tool() -> None:
    commands = cast(AutonomousCampaignCommandPort, _Commands())

    tool = AgentRuntimeProvider().campaign_proposal_tool(commands)

    assert isinstance(tool, CampaignProposalTool)


def test_apps_provider_wires_research_memory_tool() -> None:
    facade = cast(ResearchMemoryQueryFacade, object())

    tool = AgentRuntimeProvider().research_memory_tool(facade)

    assert isinstance(tool, ResearchMemoryTool)


def test_default_memory_promotion_approval_fails_closed() -> None:
    verifier = AgentRuntimeProvider().research_memory_approval_verifier()
    check = ResearchMemoryApprovalCheck(
        run_id="run-disabled",
        episode_id="episode-run-disabled",
        call_id="call-disabled",
        tool_name="research_memory_promote",
        arguments={"knowledge_id": "knowledge-disabled"},
    )

    with pytest.raises(AppCommandError) as exc_info:
        verifier.verify(check)

    assert exc_info.value.details["reason"] == "agent_feature_disabled"


def test_default_campaign_runtime_fails_closed() -> None:
    runtime = AgentRuntimeProvider().campaign_runtime()

    with pytest.raises(CampaignRuntimeUnavailable) as exc_info:
        runtime.create_campaign(
            CampaignCreateCommand(
                manifest_document={},
                idempotency_key="campaign-disabled",
            )
        )

    assert exc_info.value.reason_code == "agent_campaign_feature_disabled"
