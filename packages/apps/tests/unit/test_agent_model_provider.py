from __future__ import annotations

import pytest
from ditto_agent.models.fake import ScriptedAgentModel
from ditto_agent.models.openai_adapter import OpenAIAgentsModel
from ditto_apps.registry.agent.model_provider import (
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)


def test_agent_model_provider_defaults_to_offline_scripted_fake() -> None:
    provider = build_agent_model(AgentModelProviderSettings())

    assert isinstance(provider, ScriptedAgentModel)


def test_openai_provider_requires_feature_flag_and_a4_evidence() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.OPENAI,
        model_calls_enabled=False,
        a4_approved=False,
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
    )

    with pytest.raises(ValueError, match="model calls"):
        build_agent_model(settings)
    with pytest.raises(ValueError, match="A4"):
        build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.OPENAI,
                model_calls_enabled=True,
                a4_approved=False,
                model_id=settings.model_id,
                api_key="test-key",
                project_id="project-r5",
            )
        )


def test_openai_provider_requires_explicit_project_model_and_secret() -> None:
    with pytest.raises(ValueError, match="api_key"):
        build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.OPENAI,
                model_calls_enabled=True,
                a4_approved=True,
                model_id="gpt-5.6-terra-2026-08-01",
                api_key=None,
                project_id="project-r5",
            )
        )


def test_openai_provider_builds_adapter_without_calling_network() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.OPENAI,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
    )

    provider = build_agent_model(settings)

    assert isinstance(provider, OpenAIAgentsModel)
    assert "test-key" not in repr(settings)
