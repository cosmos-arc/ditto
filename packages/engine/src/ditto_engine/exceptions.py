"""Engine domain exception root."""

from ditto_kernel.exceptions import DittoError


class EngineError(DittoError):
    """Engine domain base exception."""


class InvalidOrderError(EngineError):
    """Invalid order or execution request."""


class BacktestConfigError(EngineError):
    """Invalid backtest configuration."""


class DataIntegrityError(EngineError):
    """Invalid or unsafe input data for engine execution."""


class PortfolioConstraintError(EngineError):
    """Portfolio or risk constraint violation."""


__all__ = [
    "BacktestConfigError",
    "DataIntegrityError",
    "EngineError",
    "InvalidOrderError",
    "PortfolioConstraintError",
]
