"""Engine domain exception root."""

from ditto_kernel.exceptions import DittoError


class EngineError(DittoError):
    """引擎域基础异常."""


__all__ = ["EngineError"]
