"""Host-owned product context to exact Agent tool authority profiles."""

from __future__ import annotations

from types import MappingProxyType

from ditto_agent.tools.registry import (
    NO_APPROVAL_TOOL_NAMES,
    READ_EVIDENCE_TOOL_ORDER,
)

__all__ = [
    "AGENT_CONTEXT_TOOL_PROFILES",
    "UnknownAgentContextProfile",
    "context_tool_allowlist",
]


class UnknownAgentContextProfile(ValueError):
    """The host received a context type without a reviewed capability profile."""


_RESEARCH_TOOLS = (
    "research_experiment_evidence",
    "research_factor_evidence",
    "research_strategy_evidence",
    "research_backtest_evidence",
)
_AUTHOR_TOOLS = (
    "author_draft_strategy",
    "author_compile_expression",
    "author_validate_strategy",
    "author_diff_strategy",
)

AGENT_CONTEXT_TOOL_PROFILES = MappingProxyType(
    {
        "market_context": ("market_context_evidence",),
        "selection": ("industry_rotation_evidence", "selection_run_evidence"),
        "instrument": ("instrument_technical_evidence",),
        "research": _RESEARCH_TOOLS,
        "experiment": ("research_experiment_evidence",),
        "factor": ("research_factor_evidence",),
        "alpha_candidate": (*_RESEARCH_TOOLS, *_AUTHOR_TOOLS),
        "strategy": ("research_strategy_evidence", *_AUTHOR_TOOLS),
        "strategy_author": (
            "selection_run_evidence",
            *_RESEARCH_TOOLS,
            *_AUTHOR_TOOLS,
        ),
        "portfolio": (
            "portfolio_evidence",
            "portfolio_comparison_evidence",
            "portfolio_scenario_preview",
            "risk_evidence",
        ),
        "manual_account": (
            "account_event_evidence",
            "portfolio_comparison_evidence",
        ),
        "daily_decision": (
            "daily_decision_v3_evidence",
            "portfolio_evidence",
            "risk_evidence",
        ),
    }
)


def _validate_profiles() -> None:
    for context_type, tools in AGENT_CONTEXT_TOOL_PROFILES.items():
        if not tools or len(set(tools)) != len(tools):
            raise RuntimeError(f"Agent context profile is invalid: {context_type}")
        unknown = tuple(tool for tool in tools if tool not in NO_APPROVAL_TOOL_NAMES)
        if unknown:
            detail = f"{context_type} {unknown}"
            raise RuntimeError(
                f"Agent context profile contains unknown tools: {detail}"
            )


_validate_profiles()


def context_tool_allowlist(context_type: str | None) -> tuple[str, ...]:
    """Return reviewed host authority or fail closed for an unknown context."""
    if context_type is None:
        return READ_EVIDENCE_TOOL_ORDER
    try:
        return AGENT_CONTEXT_TOOL_PROFILES[context_type]
    except KeyError as exc:
        raise UnknownAgentContextProfile(
            f"unrecognized Agent context profile: {context_type}"
        ) from exc
