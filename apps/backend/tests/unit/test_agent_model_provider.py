from __future__ import annotations

from typing import cast

import pytest
from ditto_agent.models.fake import ScriptedAgentModel
from ditto_agent.models.glm_adapter import GLMAgentsModel
from ditto_agent.models.openai_adapter import OpenAIAgentsModel
from ditto_apps.registry.agent.model_provider import (
    AgentModelCredentialKind,
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)


def test_agent_model_provider_defaults_to_offline_scripted_fake() -> None:
    provider = build_agent_model(AgentModelProviderSettings())

    assert isinstance(provider, ScriptedAgentModel)


def test_glm_validation_settings_load_from_explicit_apps_environment() -> None:
    settings = AgentModelProviderSettings.from_environment(
        {
            "DITTO_AGENT_MODEL_PROVIDER": "glm",
            "DITTO_AGENT_MODEL_CALLS_ENABLED": "true",
            "DITTO_AGENT_MODEL_A4_APPROVED": "true",
            "DITTO_AGENT_MODEL_ID": "glm-5.3",
            "DITTO_AGENT_MODEL_API_KEY": "test-plan-key",
            "DITTO_AGENT_MODEL_CREDENTIAL_KIND": "glm_coding_plan_validation",
            "DITTO_AGENT_MODEL_PRODUCTION_MODE": "false",
            "DITTO_AGENT_MODEL_REASONING_EFFORT": "medium",
        }
    )

    assert settings.provider is AgentModelProviderKind.GLM
    assert settings.model_calls_enabled is True
    assert settings.a4_approved is True
    assert settings.credential_kind is (
        AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
    )
    assert settings.production_mode is False
    assert settings.reasoning_effort == "medium"
    assert "test-plan-key" not in repr(settings)


def test_model_egress_license_grants_load_only_from_explicit_apps_environment() -> None:
    settings = AgentModelProviderSettings.from_environment(
        {
            "DITTO_AGENT_MODEL_APPROVED_LICENSE_CLASSES": (
                "approved-research,redistribution-reviewed"
            )
        }
    )

    assert settings.approved_license_classes == (
        "approved-research",
        "redistribution-reviewed",
    )
    assert (
        AgentModelProviderSettings.from_environment({}).approved_license_classes == ()
    )


def test_model_settings_environment_rejects_implicit_boolean_truthiness() -> None:
    with pytest.raises(ValueError, match="DITTO_AGENT_MODEL_A4_APPROVED"):
        AgentModelProviderSettings.from_environment(
            {"DITTO_AGENT_MODEL_A4_APPROVED": "approved"}
        )


def test_model_egress_license_grants_reject_duplicates_and_whitespace() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        AgentModelProviderSettings(
            approved_license_classes=("approved-research", "approved-research")
        )
    with pytest.raises(ValueError, match="surrounding whitespace"):
        AgentModelProviderSettings.from_environment(
            {
                "DITTO_AGENT_MODEL_APPROVED_LICENSE_CLASSES": (
                    "approved-research, redistribution-reviewed"
                )
            }
        )


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


def test_glm_coding_plan_provider_builds_only_for_non_production_validation() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="glm-5.3",
        api_key="test-plan-key",
        credential_kind=AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION,
        production_mode=False,
    )

    provider = build_agent_model(settings)

    assert isinstance(provider, GLMAgentsModel)
    assert "test-plan-key" not in repr(settings)


def test_glm_coding_plan_credential_is_rejected_in_production() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="glm-5.3",
        api_key="test-plan-key",
        credential_kind=AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION,
        production_mode=True,
    )

    with pytest.raises(ValueError, match="production"):
        build_agent_model(settings)


def test_glm_coding_plan_credential_fails_closed_without_environment_scope() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="glm-5.3",
        api_key="test-plan-key",
        credential_kind=AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION,
    )

    with pytest.raises(ValueError, match="production"):
        build_agent_model(settings)


def test_glm_credential_scope_rejects_unvalidated_config_strings() -> None:
    with pytest.raises(TypeError, match="credential_kind"):
        AgentModelProviderSettings(
            provider=AgentModelProviderKind.GLM,
            credential_kind=cast(
                AgentModelCredentialKind, "glm_coding_plan_validation"
            ),
        )


def test_glm_production_guard_requires_a_real_boolean() -> None:
    with pytest.raises(TypeError, match="production_mode"):
        AgentModelProviderSettings(
            provider=AgentModelProviderKind.GLM,
            production_mode=cast(bool, 0),
        )


def test_glm_formal_api_credential_remains_the_production_path() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="glm-5.3",
        api_key="test-formal-key",
        credential_kind=AgentModelCredentialKind.FORMAL_API,
        production_mode=True,
    )

    provider = build_agent_model(settings)

    assert isinstance(provider, GLMAgentsModel)


def test_glm_provider_requires_feature_flag_a4_model_and_secret() -> None:
    with pytest.raises(ValueError, match="model calls"):
        build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.GLM,
                model_calls_enabled=False,
                a4_approved=True,
                model_id="glm-5.3",
                api_key="test-plan-key",
            )
        )
    with pytest.raises(ValueError, match="A4"):
        build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.GLM,
                model_calls_enabled=True,
                a4_approved=False,
                model_id="glm-5.3",
                api_key="test-plan-key",
            )
        )
    with pytest.raises(ValueError, match="api_key"):
        build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.GLM,
                model_calls_enabled=True,
                a4_approved=True,
                model_id="glm-5.3",
                api_key=None,
            )
        )


def test_glm_coding_plan_scope_cannot_be_attached_to_openai_provider() -> None:
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.OPENAI,
        model_calls_enabled=True,
        a4_approved=True,
        model_id="gpt-5.6-terra-2026-08-01",
        api_key="test-key",
        project_id="project-r5",
        credential_kind=AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION,
    )

    with pytest.raises(ValueError, match="GLM"):
        build_agent_model(settings)
