"""Portfolio contracts type-checking tests."""

from typing import Protocol

from ditto_portfolio.contracts import PortfolioStateReader, RebalanceTarget


def test_portfolio_state_reader_is_protocol() -> None:
    assert issubclass(PortfolioStateReader, Protocol)


def test_rebalance_target_is_protocol() -> None:
    assert issubclass(RebalanceTarget, Protocol)
