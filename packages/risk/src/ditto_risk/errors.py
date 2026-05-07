"""Risk domain exception hierarchy."""

from ditto_kernel.exceptions import DittoError

__all__ = [
    "RiskConfigurationError",
    "RiskContractError",
    "RiskError",
]


class RiskError(DittoError):
    """风控域基础异常."""


class RiskConfigurationError(RiskError):
    """Invalid risk configuration that cannot produce a meaningful decision."""


class RiskContractError(RiskError):
    """Risk API contract misuse or invalid runtime context."""
