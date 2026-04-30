"""Analytics domain exception root."""

from ditto_kernel.exceptions import DittoError


class AnalyticsError(DittoError):
    """分析域基础异常."""


__all__ = ["AnalyticsError"]
