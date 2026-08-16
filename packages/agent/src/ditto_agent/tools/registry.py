"""Deterministic, capability-narrowable registry for evidence tools."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolCall, ModelToolKind, ModelToolSpec
from ditto_agent.tools._common import (
    EvidenceFunctionTool,
    read_only_tools,
)

READ_EVIDENCE_TOOL_NAMES = frozenset(
    {
        "research_experiment_evidence",
        "research_factor_evidence",
        "research_strategy_evidence",
        "research_backtest_evidence",
        "portfolio_evidence",
        "risk_evidence",
        "daily_decision_v3_evidence",
    }
)


class ToolNotAllowedError(ValueError):
    """A model requested a tool outside the host-selected read allowlist."""


class EvidenceToolRegistry:
    """Host-owned exact allowlist; model output can only select within it."""

    def __init__(self, *, tools: Iterable[EvidenceFunctionTool]) -> None:
        index: dict[str, EvidenceFunctionTool] = {}
        for tool in tools:
            spec = tool.spec
            if spec.name in index:
                raise ValueError(f"duplicate tool name: {spec.name}")
            if spec.name not in READ_EVIDENCE_TOOL_NAMES:
                raise ToolNotAllowedError(f"tool is not read-allowlisted: {spec.name}")
            if spec.kind is not ModelToolKind.FUNCTION or spec.requires_approval:
                raise ValueError(
                    "evidence registry accepts no-approval function tools only"
                )
            index[spec.name] = tool
        self._tools = read_only_tools(index)

    @property
    def tools(self) -> Mapping[str, EvidenceFunctionTool]:
        """Return the immutable name-to-tool map."""
        return self._tools

    @property
    def specs(self) -> tuple[ModelToolSpec, ...]:
        """Return provider specs in deterministic registration order."""
        return tuple(tool.spec for tool in self._tools.values())

    def restrict(self, allowed_names: tuple[str, ...]) -> EvidenceToolRegistry:
        """Create a narrower registry; missing or duplicate names fail closed."""
        if len(set(allowed_names)) != len(allowed_names):
            raise ValueError("allowed tool names must be unique")
        unknown = tuple(name for name in allowed_names if name not in self._tools)
        if unknown:
            raise ToolNotAllowedError(f"tools are not registered: {unknown}")
        return EvidenceToolRegistry(tools=(self._tools[name] for name in allowed_names))

    def execute(
        self,
        *,
        call: ModelToolCall,
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Dispatch one typed model intent with trusted host context."""
        tool = self._tools.get(call.tool_name)
        if tool is None:
            raise ToolNotAllowedError(f"tool is not allowed: {call.tool_name}")
        return tool.invoke(arguments=call.arguments, context=context)


__all__ = [
    "READ_EVIDENCE_TOOL_NAMES",
    "EvidenceToolRegistry",
    "ToolNotAllowedError",
]
