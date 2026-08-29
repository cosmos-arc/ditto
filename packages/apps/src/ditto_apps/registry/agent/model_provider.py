"""Fail-closed composition of offline and live Agent model providers."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from ditto_agent.models.fake import ScriptedAgentModel, ScriptedStep
from ditto_agent.models.glm_adapter import GLMAgentsModel, GLMEndpointKind
from ditto_agent.models.openai_adapter import (
    AgentsSDKEngine,
    OpenAIAgentsModel,
    OpenAIEngine,
    ReasoningEffort,
)
from ditto_agent.models.port import AgentModelPort, ModelToolInvoker


class AgentModelProviderKind(StrEnum):
    """Configured model provider implementation."""

    FAKE = "fake"
    OPENAI = "openai"
    GLM = "glm"


class AgentModelCredentialKind(StrEnum):
    """Operator-declared credential scope enforced by the composition root."""

    FORMAL_API = "formal_api"
    GLM_CODING_PLAN_VALIDATION = "glm_coding_plan_validation"


def _normalized_text(value: str, *, field_name: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized != normalized.strip():
        raise ValueError(
            f"{field_name} must be non-empty without surrounding whitespace"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class AgentModelProviderSettings:
    """Apps-owned provider config with all live capabilities disabled by default."""

    provider: AgentModelProviderKind = AgentModelProviderKind.FAKE
    model_calls_enabled: bool = False
    a4_approved: bool = False
    model_id: str | None = None
    api_key: str | None = field(default=None, repr=False)
    project_id: str | None = None
    credential_kind: AgentModelCredentialKind = AgentModelCredentialKind.FORMAL_API
    production_mode: bool = True
    reasoning_effort: ReasoningEffort = None

    def __post_init__(self) -> None:
        """Validate closed config identities and normalize optional secrets."""
        if not isinstance(cast(object, self.provider), AgentModelProviderKind):
            raise TypeError("provider must be an AgentModelProviderKind")
        if not isinstance(cast(object, self.credential_kind), AgentModelCredentialKind):
            raise TypeError("credential_kind must be an AgentModelCredentialKind")
        for field_name in (
            "model_calls_enabled",
            "a4_approved",
            "production_mode",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        for field_name in ("model_id", "api_key", "project_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _normalized_text(value, field_name=field_name),
                )
        if self.reasoning_effort is not None:
            normalized_effort = _normalized_text(
                self.reasoning_effort,
                field_name="reasoning_effort",
            )
            if normalized_effort not in {
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            }:
                raise ValueError("reasoning_effort is unsupported")
            object.__setattr__(
                self,
                "reasoning_effort",
                cast(ReasoningEffort, normalized_effort),
            )


def _required(
    value: str | None, *, field_name: str, provider_name: str = "OpenAI"
) -> str:
    if value is None:
        raise ValueError(f"{provider_name} provider requires {field_name}")
    return value


def build_agent_model(
    settings: AgentModelProviderSettings,
    *,
    script: tuple[ScriptedStep, ...] = (),
    openai_engine: OpenAIEngine | None = None,
    tool_invoker: ModelToolInvoker | None = None,
) -> AgentModelPort:
    """Build an offline fake or an explicitly authorized live adapter."""
    if settings.provider is AgentModelProviderKind.FAKE:
        return ScriptedAgentModel(script=script, tool_invoker=tool_invoker)
    if not settings.model_calls_enabled:
        raise ValueError("live model calls are disabled")
    if not settings.a4_approved:
        raise ValueError("live provider requires Approval A4 evidence")
    engine = openai_engine or AgentsSDKEngine(tool_invoker=tool_invoker)
    if settings.provider is AgentModelProviderKind.GLM:
        if (
            settings.credential_kind
            is AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
            and settings.production_mode
        ):
            raise ValueError(
                "GLM Coding Plan validation credentials are forbidden in production"
            )
        return GLMAgentsModel(
            model_id=_required(
                settings.model_id, field_name="model_id", provider_name="GLM"
            ),
            api_key=_required(
                settings.api_key, field_name="api_key", provider_name="GLM"
            ),
            endpoint_kind=(
                GLMEndpointKind.CODING_PLAN_RESPONSES
                if settings.credential_kind
                is AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
                else GLMEndpointKind.FORMAL_API_CHAT_COMPLETIONS
            ),
            engine=engine,
            reasoning_effort=settings.reasoning_effort,
        )
    if settings.credential_kind is AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION:
        raise ValueError("GLM Coding Plan credentials require the GLM provider")
    return OpenAIAgentsModel(
        model_id=_required(settings.model_id, field_name="model_id"),
        api_key=_required(settings.api_key, field_name="api_key"),
        project_id=_required(settings.project_id, field_name="project_id"),
        engine=engine,
        reasoning_effort=settings.reasoning_effort,
    )


__all__ = [
    "AgentModelCredentialKind",
    "AgentModelProviderKind",
    "AgentModelProviderSettings",
    "build_agent_model",
]
