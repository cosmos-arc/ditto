"""Fail-closed composition of offline and OpenAI Agent model providers."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from ditto_agent.models.fake import ScriptedAgentModel, ScriptedStep
from ditto_agent.models.openai_adapter import OpenAIAgentsModel, OpenAIEngine
from ditto_agent.models.port import AgentModelPort


class AgentModelProviderKind(StrEnum):
    """Configured model provider implementation."""

    FAKE = "fake"
    OPENAI = "openai"


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

    def __post_init__(self) -> None:
        """Validate flags and normalize optional OpenAI configuration."""
        for field_name in ("model_id", "api_key", "project_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _normalized_text(value, field_name=field_name),
                )


def _required(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"OpenAI provider requires {field_name}")
    return value


def build_agent_model(
    settings: AgentModelProviderSettings,
    *,
    script: tuple[ScriptedStep, ...] = (),
    openai_engine: OpenAIEngine | None = None,
) -> AgentModelPort:
    """Build an offline fake or an explicitly authorized OpenAI adapter."""
    if settings.provider is AgentModelProviderKind.FAKE:
        return ScriptedAgentModel(script=script)
    if not settings.model_calls_enabled:
        raise ValueError("OpenAI model calls are disabled")
    if not settings.a4_approved:
        raise ValueError("OpenAI provider requires Approval A4 evidence")
    return OpenAIAgentsModel(
        model_id=_required(settings.model_id, field_name="model_id"),
        api_key=_required(settings.api_key, field_name="api_key"),
        project_id=_required(settings.project_id, field_name="project_id"),
        engine=openai_engine,
    )


__all__ = [
    "AgentModelProviderKind",
    "AgentModelProviderSettings",
    "build_agent_model",
]
