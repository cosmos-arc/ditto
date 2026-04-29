"""Engine domain exception root."""

from ditto_kernel.exceptions import DittoError


class EngineError(DittoError):
    """引擎域基础异常."""


class StateTransitionError(EngineError):
    """Invalid domain state transition."""


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
    "StateTransitionError",
]
