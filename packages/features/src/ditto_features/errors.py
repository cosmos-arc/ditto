"""Features domain exception root."""

from ditto_kernel.exceptions import DittoError


class FeaturesError(DittoError):
    """因子域基础异常."""


__all__ = ["FeaturesError"]
