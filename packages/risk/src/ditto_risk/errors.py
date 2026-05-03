"""Risk domain exception hierarchy."""

from ditto_kernel.exceptions import DittoError

__all__ = [
    "ConstraintViolationError",
    "DrawdownThresholdError",
    "ExposureLimitError",
    "RiskError",
]


class RiskError(DittoError):
    """风控域基础异常."""


class ConstraintViolationError(RiskError):
    """约束违规异常."""


class ExposureLimitError(RiskError):
    """暴露超限异常."""


class DrawdownThresholdError(RiskError):
    """回撤超限异常."""
