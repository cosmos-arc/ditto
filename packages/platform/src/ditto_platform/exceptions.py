"""Platform exception root."""

from ditto_kernel.exceptions import DittoError


class PlatformError(DittoError):
    """平台基础设施错误根."""


__all__ = ["PlatformError"]
