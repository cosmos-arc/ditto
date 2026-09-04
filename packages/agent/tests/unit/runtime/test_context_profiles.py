"""Host context profiles must resolve to exact, fail-closed tool scopes."""

from __future__ import annotations

import pytest
from ditto_agent.runtime.context_profiles import (
    UnknownAgentContextProfile,
    context_tool_allowlist,
)
from ditto_agent.tools.registry import (
    NO_APPROVAL_TOOL_NAMES,
    READ_EVIDENCE_TOOL_NAMES,
)


@pytest.mark.parametrize(
    ("context_type", "expected"),
    [
        ("market_context", ("market_context_evidence",)),
        (
            "selection",
            ("industry_rotation_evidence", "selection_run_evidence"),
        ),
        ("instrument", ("instrument_technical_evidence",)),
        (
            "research",
            (
                "research_experiment_evidence",
                "research_factor_evidence",
                "research_strategy_evidence",
                "research_backtest_evidence",
            ),
        ),
        (
            "strategy_author",
            (
                "selection_run_evidence",
                "research_experiment_evidence",
                "research_factor_evidence",
                "research_strategy_evidence",
                "research_backtest_evidence",
                "author_draft_strategy",
                "author_compile_expression",
                "author_validate_strategy",
                "author_diff_strategy",
            ),
        ),
        (
            "portfolio",
            (
                "portfolio_evidence",
                "portfolio_comparison_evidence",
                "portfolio_scenario_preview",
                "risk_evidence",
            ),
        ),
        (
            "manual_account",
            ("account_event_evidence", "portfolio_comparison_evidence"),
        ),
    ],
)
def test_context_profile_resolves_exact_capability_subset(
    context_type: str,
    expected: tuple[str, ...],
) -> None:
    resolved = context_tool_allowlist(context_type)

    assert resolved == expected
    assert set(resolved) <= NO_APPROVAL_TOOL_NAMES


def test_missing_context_uses_the_full_host_read_profile() -> None:
    resolved = context_tool_allowlist(None)

    assert set(resolved) == READ_EVIDENCE_TOOL_NAMES


def test_unknown_context_fails_closed_instead_of_receiving_every_tool() -> None:
    with pytest.raises(UnknownAgentContextProfile, match="unrecognized"):
        context_tool_allowlist("model-invented-context")
