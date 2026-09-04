"""Apps composition registers both grounded portfolio tools over Application."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_agent.tools.account_event import AccountEventEvidenceTool
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_apps.registry.agent.model_provider import AgentModelProviderSettings
from ditto_apps.registry.agent.provider import (
    AgentRuntimeProvider,
    AgentRuntimeResources,
)
from ditto_apps.registry.agent.runtime import PersistedAgentRuntimeOptions
from ditto_apps.registry.agent.settings import AgentFeatureSettings


def test_agent_registry_wires_comparison_and_preview_without_write_tools() -> None:
    provider = AgentRuntimeProvider()
    core = provider.core_evidence_tools(
        decision=MagicMock(),
        market_context=MagicMock(),
        industry_rotation=MagicMock(),
        selection_run=MagicMock(),
        technical_analysis=MagicMock(),
    )
    workflows = provider.workflow_evidence_tools(
        research=MagicMock(),
        portfolio_comparison=MagicMock(),
        authoring_preview=MagicMock(),
        account_event=MagicMock(),
    )
    registry = provider.evidence_tool_registry(core=core, workflows=workflows)

    names = tuple(spec.name for spec in registry.specs)
    assert "portfolio_comparison_evidence" in names
    assert "portfolio_scenario_preview" in names
    assert "account_event_evidence" in names
    assert isinstance(
        registry.tools["account_event_evidence"],
        AccountEventEvidenceTool,
    )
    assert {
        "author_draft_strategy",
        "author_compile_expression",
        "author_validate_strategy",
        "author_diff_strategy",
    } <= set(names)
    assert "publish_strategy" not in names
    assert not any(
        fragment in name
        for name in names
        for fragment in ("apply", "write", "order", "broker")
    )


def test_agent_registry_passes_explicit_license_grants_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, PersistedAgentRuntimeOptions] = {}

    def capture_runtime(**kwargs: object) -> object:
        options = kwargs["options"]
        assert isinstance(options, PersistedAgentRuntimeOptions)
        captured["options"] = options
        return object()

    monkeypatch.setattr(
        "ditto_apps.registry.agent.provider.PersistedAgentRuntime",
        capture_runtime,
    )
    database = MagicMock()
    result = AgentRuntimeProvider().runtime(
        AgentFeatureSettings(agent_enabled=True, model_calls_enabled=True),
        AgentModelProviderSettings(approved_license_classes=("approved-research",)),
        EvidenceToolRegistry(tools=()),
        AgentRuntimeResources(
            database=database,
            manifest=MagicMock(),
            decision_store=None,
        ),
    )

    assert result is not None
    assert captured["options"].approved_license_classes == ("approved-research",)
