"""Composition-root wiring for the Campaign proposal tool."""

from typing import cast

from ditto_agent.tools.campaign import CampaignProposalTool
from ditto_application.agent_campaign_contracts import AutonomousCampaignCommandPort
from ditto_apps.registry.agent.provider import AgentRuntimeProvider


class _Commands:
    pass


def test_apps_provider_wires_campaign_proposal_tool() -> None:
    commands = cast(AutonomousCampaignCommandPort, _Commands())

    tool = AgentRuntimeProvider().campaign_proposal_tool(commands)

    assert isinstance(tool, CampaignProposalTool)
