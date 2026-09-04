"""GLM Responses adapter with a fixed Ditto validation data boundary."""

from __future__ import annotations

from enum import StrEnum

from ditto_agent.models.openai_adapter import (
    OpenAICompatibleAgentsModel,
    OpenAIEngine,
    ReasoningEffort,
)

GLM_CODING_PLAN_RESPONSES_BASE_URL = "https://open.bigmodel.cn/api/v1"
GLM_FORMAL_API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_RESPONSES_BASE_URL = GLM_CODING_PLAN_RESPONSES_BASE_URL


class GLMEndpointKind(StrEnum):
    """Credential-bound GLM endpoint families that must never be interchanged."""

    CODING_PLAN_RESPONSES = "coding_plan_responses"
    FORMAL_API_CHAT_COMPLETIONS = "formal_api_chat_completions"


class GLMAgentsModel(OpenAICompatibleAgentsModel):
    """GLM's OpenAI-compatible Responses endpoint behind AgentModelPort."""

    _provider_name = "GLM"

    def __init__(
        self,
        *,
        model_id: str,
        api_key: str,
        endpoint_kind: GLMEndpointKind,
        engine: OpenAIEngine | None = None,
        reasoning_effort: ReasoningEffort = None,
    ) -> None:
        if type(endpoint_kind) is not GLMEndpointKind:
            raise TypeError("endpoint_kind must be a GLMEndpointKind")
        coding_plan = endpoint_kind is GLMEndpointKind.CODING_PLAN_RESPONSES
        super().__init__(
            model_id=model_id,
            api_key=api_key,
            engine=engine,
            base_url=(
                GLM_CODING_PLAN_RESPONSES_BASE_URL
                if coding_plan
                else GLM_FORMAL_API_BASE_URL
            ),
            provider_id="glm_agents" if coding_plan else "glm_formal_api_agents",
            use_responses=coding_plan,
            reasoning_effort=reasoning_effort,
        )
        self._native_structured_outputs = not coding_plan


__all__ = [
    "GLM_CODING_PLAN_RESPONSES_BASE_URL",
    "GLM_FORMAL_API_BASE_URL",
    "GLM_RESPONSES_BASE_URL",
    "GLMAgentsModel",
    "GLMEndpointKind",
]
