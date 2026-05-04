"""Strategy public-boundary error tests."""

from __future__ import annotations

import pytest
from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec
from ditto_strategy.alpha.validation import validate_spec_params
from ditto_strategy.errors import StrategySpecError


def test_validate_spec_params_raises_strategy_spec_error_for_missing_param() -> None:
    """Public StrategySpec validation failures use the strategy domain error."""
    spec = StrategySpec(
        strategy_id="momentum",
        name="momentum",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        params={},
        param_constraints=(ParamConstraint(name="lookback", dtype="int"),),
    )

    with pytest.raises(StrategySpecError) as exc_info:
        validate_spec_params(spec)

    assert exc_info.value.details["param_name"] == "lookback"
    assert exc_info.value.details["reason"] == "missing_param"
