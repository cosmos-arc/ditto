"""Risk-owned exposure and stress preview boundary tests."""

from __future__ import annotations

import pytest
from ditto_risk.portfolio_scenario import (
    PortfolioScenarioInput,
    ScenarioPosition,
    preview_portfolio_scenario,
)


def test_scenario_preview_reports_exposure_turnover_constraints_and_stress() -> None:
    preview = preview_portfolio_scenario(
        PortfolioScenarioInput(
            as_of="2026-08-31",
            valuation_snapshot_id="valuation:snapshot-1",
            source_snapshot_ids=("snapshot:stock",),
            current_positions=(
                ScenarioPosition(600519, 0.60, "consumer"),
                ScenarioPosition(510300, 0.30, "fund"),
            ),
            proposed_positions=(
                ScenarioPosition(600519, 0.50, "consumer"),
                ScenarioPosition(510300, 0.40, "fund"),
            ),
            cash_reserve_weight=0.10,
            max_position_weight=0.50,
            market_shock=-0.10,
            industry_shocks={"consumer": -0.20},
        )
    )

    assert preview.turnover == pytest.approx(0.10)
    assert preview.before.gross_exposure == pytest.approx(0.90)
    assert preview.after.industry_exposure == {
        "consumer": pytest.approx(0.50),
        "fund": pytest.approx(0.40),
    }
    assert preview.before.stressed_return == pytest.approx(-0.21)
    assert preview.after.stressed_return == pytest.approx(-0.19)
    assert preview.constraint_findings == ()


def test_scenario_boundary_values_are_findings_not_hidden_exceptions() -> None:
    preview = preview_portfolio_scenario(
        PortfolioScenarioInput(
            as_of="2026-08-31",
            valuation_snapshot_id="valuation:snapshot-1",
            source_snapshot_ids=("snapshot:stock",),
            current_positions=(ScenarioPosition(1, 0.90, "a"),),
            proposed_positions=(ScenarioPosition(1, 0.51, "a"),),
            cash_reserve_weight=0.49,
            max_position_weight=0.50,
        )
    )

    assert preview.constraint_findings == ("MAX_POSITION_WEIGHT:1",)


@pytest.mark.parametrize("weight", [-0.01, float("nan"), float("inf")])
def test_scenario_contract_rejects_invalid_weights(weight: float) -> None:
    with pytest.raises(ValueError, match="weight"):
        preview_portfolio_scenario(
            PortfolioScenarioInput(
                as_of="2026-08-31",
                valuation_snapshot_id="valuation:snapshot-1",
                source_snapshot_ids=("snapshot:stock",),
                current_positions=(ScenarioPosition(1, 0.50, "a"),),
                proposed_positions=(ScenarioPosition(1, weight, "a"),),
                cash_reserve_weight=0.50,
                max_position_weight=0.50,
            )
        )
