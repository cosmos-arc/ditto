"""Portfolio error hierarchy tests."""

from ditto_kernel.exceptions import DittoError
from ditto_portfolio.errors import PortfolioError, StateTransitionError


def test_portfolio_error_hierarchy() -> None:
    assert issubclass(PortfolioError, DittoError)
    assert issubclass(StateTransitionError, PortfolioError)


def test_state_transition_error_carries_details() -> None:
    err = StateTransitionError("invalid transition", current="filled", target="open")
    assert err.details == {"current": "filled", "target": "open"}
