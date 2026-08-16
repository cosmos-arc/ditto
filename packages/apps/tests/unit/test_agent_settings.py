from __future__ import annotations

import pytest
from ditto_apps.registry.agent.settings import AgentFeatureSettings


def test_agent_feature_flags_default_false() -> None:
    settings = AgentFeatureSettings.from_environment({})

    assert settings.agent_enabled is False
    assert settings.author_enabled is False
    assert settings.campaign_enabled is False
    assert settings.decision_shadow_enabled is False
    assert settings.model_calls_enabled is False
    assert settings.any_enabled is False


def test_agent_feature_flags_use_only_fixed_environment_names() -> None:
    settings = AgentFeatureSettings.from_environment(
        {
            "DITTO_AGENT_ENABLED": "true",
            "DITTO_AGENT_AUTHOR_ENABLED": "1",
            "DITTO_AGENT_CAMPAIGN_ENABLED": "TRUE",
            "DITTO_AGENT_DECISION_SHADOW_ENABLED": "yes",
            "DITTO_AGENT_MODEL_CALLS_ENABLED": "on",
            "AGENT_ENABLED": "false",
        }
    )

    assert settings.agent_enabled is True
    assert settings.author_available is True
    assert settings.campaign_available is True
    assert settings.decision_shadow_available is True
    assert settings.model_calls_available is True


def test_child_flags_remain_effectively_disabled_without_master_flag() -> None:
    settings = AgentFeatureSettings.from_environment(
        {
            "DITTO_AGENT_AUTHOR_ENABLED": "true",
            "DITTO_AGENT_CAMPAIGN_ENABLED": "true",
            "DITTO_AGENT_DECISION_SHADOW_ENABLED": "true",
            "DITTO_AGENT_MODEL_CALLS_ENABLED": "true",
        }
    )

    assert settings.any_enabled is False
    assert settings.author_available is False
    assert settings.campaign_available is False
    assert settings.decision_shadow_available is False
    assert settings.model_calls_available is False


def test_invalid_feature_flag_fails_closed() -> None:
    with pytest.raises(ValueError, match="DITTO_AGENT_ENABLED"):
        AgentFeatureSettings.from_environment({"DITTO_AGENT_ENABLED": "enabled"})
