"""Boundary validation for read-only portfolio scenario evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_risk.portfolio_scenario import (
    PortfolioScenarioInput,
    ScenarioPosition,
    preview_portfolio_scenario,
)


def _scenario() -> PortfolioScenarioInput:
    return PortfolioScenarioInput(
        as_of="2026-09-04",
        valuation_snapshot_id="valuation:1",
        source_snapshot_ids=("source:1",),
        current_positions=(ScenarioPosition(1, 0.4, None),),
        proposed_positions=(ScenarioPosition(1, 0.4, None),),
        cash_reserve_weight=0.1,
        max_position_weight=0.5,
    )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"as_of": ""}, "exact as_of"),
        ({"valuation_snapshot_id": ""}, "exact as_of"),
        ({"source_snapshot_ids": ()}, "source snapshot"),
        ({"source_snapshot_ids": ("a", "a")}, "source snapshot"),
        ({"cash_reserve_weight": float("nan")}, "constraints"),
        ({"cash_reserve_weight": 1.0}, "constraints"),
        ({"max_position_weight": 0.0}, "constraints"),
        ({"max_position_weight": float("inf")}, "constraints"),
        ({"market_shock": float("nan")}, "market_shock"),
        ({"industry_shocks": {"": -0.1}}, "industry shocks"),
        ({"industry_shocks": {"technology": float("inf")}}, "industry shocks"),
    ],
)
def test_scenario_requires_complete_finite_authority(
    changes: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        preview_portfolio_scenario(replace(_scenario(), **changes))


@pytest.mark.parametrize(
    ("position", "match"),
    [
        (ScenarioPosition(0, 0.1, "industry"), "identity"),
        (ScenarioPosition(1, 0.1, " "), "industry"),
    ],
)
def test_scenario_positions_require_identity_and_named_industry(
    position: ScenarioPosition,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        preview_portfolio_scenario(replace(_scenario(), proposed_positions=(position,)))


def test_scenario_rejects_duplicate_positions_and_total_weight_over_one() -> None:
    with pytest.raises(ValueError, match="identity"):
        preview_portfolio_scenario(
            replace(
                _scenario(),
                proposed_positions=(
                    ScenarioPosition(1, 0.2),
                    ScenarioPosition(1, 0.3),
                ),
            )
        )
    with pytest.raises(ValueError, match="weights exceed one"):
        preview_portfolio_scenario(
            replace(
                _scenario(),
                proposed_positions=(
                    ScenarioPosition(1, 0.6),
                    ScenarioPosition(2, 0.5),
                ),
            )
        )


def test_scenario_reports_cash_reserve_and_unclassified_exposure() -> None:
    preview = preview_portfolio_scenario(
        replace(
            _scenario(),
            proposed_positions=(ScenarioPosition(1, 0.6, None),),
            cash_reserve_weight=0.5,
            max_position_weight=1.0,
        )
    )

    assert preview.after.industry_exposure == {"unclassified": 0.6}
    assert preview.constraint_findings == ("CASH_RESERVE_WEIGHT",)
