"""Portfolio domain exception root."""

from ditto_kernel.exceptions import DittoError


class PortfolioError(DittoError):
    """Portfolio domain base exception."""


class StateTransitionError(PortfolioError):
    """Invalid domain state transition."""


__all__ = [
    "PortfolioError",
    "StateTransitionError",
]
